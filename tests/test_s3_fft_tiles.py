import concurrent.futures
import ctypes
import json
import os
from pathlib import Path
import random
import subprocess
import tempfile
import threading
import unittest

try:
    import numpy as np
except ImportError:
    raise unittest.SkipTest("Optional host FFT oracle needs NumPy; the S3 offline workflow installs it")

ROOT = Path(__file__).resolve().parents[1]


class FFTTilesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.measurements = []
        cls.temp = tempfile.TemporaryDirectory()
        shared = Path(cls.temp.name) / "tiles.so"
        subprocess.run(["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-fPIC", "-shared", "-fsanitize=undefined", "-fno-sanitize-recover=undefined",
                        "experiments/s3_fft_tiles.c", "-o", str(shared)], cwd=ROOT, check=True)
        cls.lib = ctypes.CDLL(str(shared))
        cls.pointer = ctypes.POINTER(ctypes.c_int16)
        cls.lib.s3_fft_reverse_tile.argtypes = [cls.pointer, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
        cls.lib.s3_fft_stage_tile.argtypes = [cls.pointer, cls.pointer, *([ctypes.c_uint] * 4)]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
        if os.environ.get("S3_FFT_REPORT"):
            Path(os.environ["S3_FFT_REPORT"]).write_text(json.dumps({
                "scope": "Scalar functional reference on host; not S3 SIMD or WCET measurement",
                "NumPy_version": np.__version__, "measurements": cls.measurements,
                "Q15_test_error_limit_LSB": 8,
                "S3_500us_deadline_verified": False,
                "8192_point_twiddle_bytes": 16384,
            }, indent=2) + "\n")

    def transform(self, samples, parallel):
        n = len(samples)
        data = np.empty(2*n, dtype=np.int16)
        data[::2] = samples.real; data[1::2] = samples.imag
        angle = -2 * np.pi * np.arange(n//2) / n
        twiddle = np.empty(n, dtype=np.int16)
        twiddle[::2] = np.clip(np.rint(32768*np.cos(angle)), -32768, 32767).astype(np.int16)
        twiddle[1::2] = np.clip(np.rint(32768*np.sin(angle)), -32768, 32767).astype(np.int16)
        dp, wp = data.ctypes.data_as(self.pointer), twiddle.ctypes.data_as(self.pointer)
        phases = [(0, n)] + [(1 << i, n//2) for i in range(1, n.bit_length())]
        barrier = threading.Barrier(2)

        def worker(core):
            for span, count in phases:
                starts = list(range(64*core, count, 128))
                random.Random(span + core).shuffle(starts)
                for start in starts:
                    end = min(start + 64, count)
                    if span == 0:
                        self.lib.s3_fft_reverse_tile(dp, n, start, end)
                    else:
                        self.lib.s3_fft_stage_tile(dp, wp, n, span, start, end)
                barrier.wait(timeout=10)

        if parallel:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                jobs = [pool.submit(worker, core) for core in (0, 1)]
                for job in jobs:
                    job.result(timeout=30)
        else:
            for span, count in phases:
                if span == 0:
                    self.lib.s3_fft_reverse_tile(dp, n, 0, count)
                else:
                    self.lib.s3_fft_stage_tile(dp, wp, n, span, 0, count)
        return data[::2].astype(float) + 1j * data[1::2].astype(float)

    def test_parallel_tiles_match_sequential_and_independent_fft(self):
        rng = np.random.default_rng(8123)
        for n in (32, 256, 8192):
            phase = np.arange(n)
            inputs = {
                "zero": np.zeros(n, dtype=complex),
                "DC": np.full(n, 1000+2000j),
                "impulse": np.r_[12000+6000j, np.zeros(n-1)],
                "tone": np.rint(4000*np.cos(2*np.pi*7*phase/n)) +
                        1j*np.rint(4000*np.sin(2*np.pi*7*phase/n)),
                "noise": rng.integers(-8000, 8000, n) + 1j*rng.integers(-8000, 8000, n),
            }
            for name, signal in inputs.items():
                with self.subTest(n=n, name=name):
                    actual = self.transform(signal, True)
                    np.testing.assert_array_equal(actual, self.transform(signal, False))
                    reference = np.fft.fft(signal) / n
                    error = float(np.max(np.abs(actual - reference)))
                    self.measurements.append({"n": n, "input": name,
                                              "parallel_matches_sequential": True,
                                              "maximum_complex_error_LSB": error})
                    self.assertLessEqual(error, 8,
                                         "Q15 error exceeds declared 8-LSB test envelope")


if __name__ == "__main__":
    unittest.main()
