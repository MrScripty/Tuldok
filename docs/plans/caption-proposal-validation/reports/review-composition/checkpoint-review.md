Independent composition review checkpoint

Source: e89cf7636e3b6790179a0de3f4aeb9c433217bed
Tree: ea56fd0702b8b65a8ca2c60288fffce88c512a5d

No P1/P2 found in the bounded static frontend-versus-backend validation class tested here. The separately reported storage-envelope P2 remains open at this checkpoint and requires successor review; this is not a final approval of that checkpoint.

The external probe loaded production captionProposalRecoveryBody in a VM and checked 14,058 cases against the actual Python ai_http.validate_url/validate_model and workbench.text_value. It covered all 29 Python whitespace characters; all 2,048 unpaired surrogate code points in each text field; C0 characters; ASCII/non-BMP exact boundaries and whitespace normalization; HTTP/HTTPS authority, ports, credentials, query/fragment, NFKC delimiters and bracket forms; IDs, revision and seed shape. No body accepted by the frontend was rejected by the backend. All 1,286 accepted bodies returned unchanged field values.

The 542 conservative frontend refusals are Python-permissive URL forms (IPvFuture, malformed bracket suffixes, DEL/percent host forms, authority backslashes) and two revisions beyond JS safe integers. Strict parser parity is not claimed, and these cases do not establish an ordinary-form reachability defect or a security defect. WHATWG parser restrictions mostly predate this repair.

CAPTION_RELOAD_CASE=input node tests/test_caption_reload_controller.cjs passed: 86 real-backend oracle cases plus fresh correction without durable storage errors and lost-error/404/reload exact identity fencing. Browser/aggregate execution belongs to the root; none was run by this review.

Dynamic source state, real model quality and general URL transport compatibility are outside this static review. Historical invalid recovery evidence deliberately remains fenced; validation cannot prove whether an earlier network attempt was admitted.
