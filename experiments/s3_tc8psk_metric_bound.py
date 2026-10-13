"""Exact piecewise-linear bound for Q15 / COST_SHIFT=22 path arithmetic.

Within each cone defined by the four projection zero lines, a difference of
absolute projections is linear. Its maximum and minimum over the bounded
input rectangle occur at vertices of that cone/rectangle intersection.
Enumerating every intersection of the zero lines and rectangle boundaries
therefore bounds ALL 2**32 signed-Q15 input pairs, without sampling them.
Rounding with a common offset changes a difference by at most ceil(delta/Q);
clamping to [0,511] cannot increase it. See the path-pair proof in the report.
"""
from fractions import Fraction
from itertools import combinations
import json


def bound():
    projections=((32768,0),(-23170,23170),(23170,23170),(0,32768))
    lines=[(1,0,-32768),(1,0,32767),(0,1,-32768),(0,1,32767)]
    lines += [(a,b,0) for a,b in projections]
    vertices=set()
    for (a,b,c),(d,e,f) in combinations(lines,2):
        determinant=a*e-b*d
        if determinant:
            i=Fraction(c*e-b*f,determinant)
            q=Fraction(a*f-c*d,determinant)
            if -32768<=i<=32767 and -32768<=q<=32767:
                vertices.add((i,q))
    delta={0:0};projection_bounds={}
    for label_xor in (1,2,3):
        maximum=max(abs(abs(projections[j][0]*i+projections[j][1]*q)-
                        abs(projections[j^label_xor][0]*i+projections[j^label_xor][1]*q))
                    for j in range(4) for i,q in vertices)
        assert maximum.denominator==1
        projection_bounds[label_xor]=int(maximum)
        delta[label_xor]=(int(maximum)+(1<<22)-1)//(1<<22)
    history=0;impulse=[]
    for bit in (1,0,0,0,0,0,0):
        history=(history<<1)|bit
        x=(history&0o171).bit_count()&1
        y=(history&0o133).bit_count()&1
        impulse.append(2*x+y)
    candidate_bound=sum(delta[x] for x in impulse)
    assert impulse==[3,1,0,3,3,2,3]
    assert delta=={0:0,1:256,2:256,3:363}
    assert candidate_bound==1964 and candidate_bound<(1<<11)
    return dict(input_range=[-32768,32767],cost_shift=22,input_precision_changed=False,
        vertices=[[str(i),str(q)] for i,q in sorted(vertices)],
        absolute_projection_difference_bounds=projection_bounds,
        rounded_branch_difference_bounds=delta,encoder_impulse_label_xor=impulse,
        merging_candidate_difference_bound=candidate_bound,half_modulus=2048,
        smallest_width_certified_by_this_bound=12,
        scope='only fixed Q15 metric unit, equal initial metrics and 171/133 K7 trellis; not arbitrary 9-bit costs')

if __name__=='__main__':print(json.dumps(bound(),indent=2))
