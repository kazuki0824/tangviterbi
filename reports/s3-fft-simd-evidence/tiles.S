// Copyright 2018-2019 Espressif Systems (Shanghai) PTE LTD
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License. 

/* Derived vector loops; new ABI/setup/loop count, same pinned arithmetic. */
.section .iram1,"ax"
.literal_position
.literal .Ls3_tile_scale,32767
.align 4
.global s3_fft_simd_general
.type s3_fft_simd_general,@function
s3_fft_simd_general:
 entry a1,64
 movi a8,16
 wsr.sar a8
 l32r a7,.Ls3_tile_scale
 s16i a7,a1,0
 mov.n a6,a1
 ee.vldbc.16.ip q6,a6,0
 ee.vldbc.32.ip q5,a4,0
 loopnez a5,.Ls3_fft_simd_general_end
	ee.vld.128.ip	q0,a3,0         	# [0*II+0]  id:217
	ee.vld.128.ip	q2,a2,0         	# [0*II+1]  id:216
	ee.cmul.s16	q1,q5,q0,2        	# [0*II+2]  
	ee.vmul.s16	q2,q2,q6          	# [0*II+3]  
	ee.cmul.s16	q1,q5,q0,3        	# [0*II+4]  
	ee.vsubs.s16	q3,q2,q1         	# [0*II+6]  
	ee.vadds.s16.st.incp	q3,a3,q3,q2,q1 	# [0*II+7]  id:221
	ee.vst.128.ip	q3,a2,16        	# [0*II+8]  id:222

.Ls3_fft_simd_general_end:
 retw.n
.align 4
.global s3_fft_simd_pair
.type s3_fft_simd_pair,@function
s3_fft_simd_pair:
 entry a1,64
 movi a8,16
 wsr.sar a8
 l32r a7,.Ls3_tile_scale
 s16i a7,a1,0
 mov.n a6,a1
 ee.vldbc.16.ip q6,a6,0
 loopnez a4,.Ls3_fft_simd_pair_end
	ee.vld.l.64.ip	q0,a2,8        	# [0*II+0]  id:225
	ee.vldbc.32.ip	q2,a3,4        	# [0*II+1]  id:223
	ee.vld.l.64.ip	q1,a2,8        	# [0*II+2]  id:226
	ee.vldbc.32.ip	q3,a3,4        	# [0*II+3]  id:224
	ee.vld.h.64.ip	q0,a2,8        	# [0*II+4]  id:227
	ee.vunzip.32	q2,q3            	# [0*II+5]  
	ee.vld.h.64.ip	q1,a2,-24      	# [0*II+6]  id:228
	ee.vmul.s16	q0,q0,q6          	# [0*II+7]  
	ee.cmul.s16	q4,q2,q1,2        	# [0*II+8]  
	ee.cmul.s16	q4,q2,q1,3        	# [0*II+9]  
	ee.vadds.s16	q2,q0,q4         	# [0*II+11]  
	ee.vsubs.s16	q3,q0,q4         	# [0*II+12]  
	ee.vst.l.64.ip	q2,a2,8        	# [0*II+13]  id:232
	ee.vst.l.64.ip	q3,a2,8        	# [0*II+14]  id:233
	ee.vst.h.64.ip	q2,a2,8        	# [0*II+15]  id:234
	ee.vst.h.64.ip	q3,a2,8        	# [0*II+16]  id:235

.Ls3_fft_simd_pair_end:
 retw.n
.align 4
.global s3_fft_simd_final
.type s3_fft_simd_final,@function
s3_fft_simd_final:
 entry a1,64
 movi a8,16
 wsr.sar a8
 l32r a7,.Ls3_tile_scale
 s16i a7,a1,0
 mov.n a6,a1
 ee.vldbc.16.ip q6,a6,0
 loopnez a4,.Ls3_fft_simd_final_end
	ee.vld.128.ip	q0,a2,16        	# [0*II+0]  id:237
	ee.vld.128.ip	q1,a2,-16       	# [0*II+1]  id:238
	ee.vld.128.ip	q2,a3,16        	# [0*II+2]  id:236
	ee.vunzip.32	q0,q1            	# [0*II+3]  
	ee.cmul.s16	q3,q2,q1,2        	# [0*II+4]  
	ee.vmul.s16	q0,q0,q6          	# [0*II+5]  
	ee.cmul.s16	q3,q2,q1,3        	# [0*II+6]  
	ee.vsubs.s16	q1,q0,q3         	# [0*II+8]  
	ee.vadds.s16	q0,q0,q3         	# [0*II+9]  
	ee.vzip.32	q0,q1              	# [0*II+10]  
	ee.vst.128.ip	q0,a2,16        	# [0*II+11]  id:242
	ee.vst.128.ip	q1,a2,16        	# [0*II+12]  id:243

.Ls3_fft_simd_final_end:
 retw.n
