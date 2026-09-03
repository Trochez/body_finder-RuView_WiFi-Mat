#!/usr/bin/env python3
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'apps/mobile/src/authority.ts'
t=p.read_text(encoding='utf-8')
old="const authority_pin_state=s.pinned?'PINNED':'UNPINNED';return{schema:'AuthorityStatusV2',view,canonical_cohort_input:view.cohort,base_digest:view.base_digest,authority_view_digest:view.authority_view_digest,coordinator_generation:view.coordinator_generation,authority_pin_state,pinned_identity_digest:s.pinnedCohortDigest,pin_invalidated_reason:s.pinInvalidatedReason,pin_history:s.pinHistory,"
new="const authorityState=state(sid),authority_pin_state=authorityState.pinned?'PINNED':'UNPINNED';return{schema:'AuthorityStatusV2',view,canonical_cohort_input:view.cohort,base_digest:view.base_digest,authority_view_digest:view.authority_view_digest,coordinator_generation:view.coordinator_generation,authority_pin_state,pinned_identity_digest:authorityState.pinnedCohortDigest,pin_invalidated_reason:authorityState.pinInvalidatedReason,pin_history:authorityState.pinHistory,"
if new not in t:
    if t.count(old)!=1:raise SystemExit(f'authority post-patch anchor count={t.count(old)}')
    p.write_text(t.replace(old,new,1),encoding='utf-8')
print('DEV20_18_POST_PATCH_OK')
