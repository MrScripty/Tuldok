Independent final composition review

Source: 9483d4a2f5c1391b3f882e107cee6846aeb36a39
Tree: 0fe33807c03e582c3a5ce9f4403be37e570e8f59

No open P1/P2 findings in the reviewed static admission and recovery-envelope validation class. The initial checkpoint remains separately preserved.

Re-ran the independent 14,058-case real Python versus production JavaScript matrix: zero frontend-accepted/backend-rejected bodies, 1,286 accepted bodies with exact field values preserved. Coverage includes every Python whitespace character, every unpaired surrogate code point in every relevant text field, C0 controls, Unicode/ASCII exact bounds, URL authority/scheme/ports/userinfo/query/fragment/NFKC, IDs, revisions and seed types.

Added 36 independent persistence-envelope cases using raw trailing slashes and leading/trailing ASCII spaces, tabs, U+0085 and U+3000. All are backend-valid after backend URL normalization. The frontend accepted all nine exact-32,768-UTF-16-unit envelopes and rejected all 18 over-limit envelopes before storage, with no mismatches or normalization of accepted values. Backend URL bounds and recovery-envelope bounds are deliberately distinct contracts.

The registered input controller passed, including fresh correction, legacy invalid evidence retention, lost-error/404/reload fencing and explicit unchanged replay. The source and backend validator bytes were independently checked against the exact commit. Root owns aggregate and Chromium evidence; this reviewer ran neither.

Limits: 542 conservative frontend refusals remain for Python-permissive URL forms and two revisions beyond JS safe integers. Exact bidirectional URL parser parity and ordinary-form reachability of all URL/model invalid forms are not claimed. Dynamic source admission conflicts, transport compatibility and real model quality are outside this static review. Historical invalid evidence remains intentionally fenced; no unknown outcome is cleared or inference automatically replayed.
