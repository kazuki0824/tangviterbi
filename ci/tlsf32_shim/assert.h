#pragma once
void replay_abort(void);
#define assert(x) ((x)?(void)0:replay_abort())
