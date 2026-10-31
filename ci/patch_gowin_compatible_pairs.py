from pathlib import Path
import sys
p=Path(sys.argv[1])/'himbaechel/uarch/gowin/pack_luts.cc'
s=p.read_text(); needle='    log_info("Constrained %d LUTFF pairs.\\n", lutffs);'
addition=r'''
    // Experimental: pair only isolated LUT/FF clusters with identical controls.
    // No cells, nets or legality predicates are changed.
    std::map<std::string, std::vector<CellInfo *>> groups;
    for (auto &entry : ctx->cells) {
        CellInfo *lut = entry.second.get();
        if (!lut_outs.count(CellTypePort(lut->type, id_F)) || lut->cluster != lut->name ||
            lut->constr_abs_z || lut->constr_children.size() != 1)
            continue;
        CellInfo *ff = lut->constr_children.front();
        if (!dff_ins.count(CellTypePort(ff->type, id_D)) || ff->constr_abs_z ||
            ff->constr_x != 0 || ff->constr_y != 0 || ff->constr_z != 1 ||
            !ff->constr_children.empty())
            continue;
        std::string key = ff->type.str(ctx);
        for (IdString port : {id_CLK, id_CE, id_SET, id_RESET, id_PRESET, id_CLEAR}) {
            NetInfo *net = ff->getPort(port);
            key += "|" + std::to_string(net ? net->name.index : 0);
        }
        groups[key].push_back(lut);
    }
    int paired = 0;
    for (auto &group : groups) {
        auto &roots = group.second;
        std::sort(roots.begin(), roots.end(), [&](CellInfo *a, CellInfo *b) {
            return a->name.str(ctx) < b->name.str(ctx);
        });
        for (size_t i = 0; i + 1 < roots.size(); i += 2) {
            CellInfo *a = roots[i], *b = roots[i + 1];
            CellInfo *bf = b->constr_children.front();
            b->constr_children.clear();
            b->cluster = a->name;
            b->constr_x = b->constr_y = 0;
            b->constr_z = 2;
            bf->cluster = a->name;
            bf->constr_z = 3;
            a->constr_children.push_back(b);
            a->constr_children.push_back(bf);
            ++paired;
        }
    }
    log_info("TANG compatible double LUTFF clusters: %d.\n", paired);
'''
assert s.count(needle)==1
p.write_text(s.replace(needle,needle+addition).replace('#include <cinttypes>','#include <cinttypes>\n#include <map>'))
