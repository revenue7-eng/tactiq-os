# Altered sets for release and L3 checkers

Altered and forged copies of the v2.1.0-rc14 release, for testing a checker
against inputs it must refuse. Written by Capt Anil Sharma
(<https://ankr.in/tactiq-verification.html>) and placed here with his
permission, under the licence of this repository.

| File | Bytes | SHA-256 |
|---|---|---|
| `tactiq-altered-sets.py` | 31386 | `5556fed2903defb1fbd997f741ab0c098ba5ad4886b0b88c68acffa9f1386547` |
| `tactiq-altered-sets-rc14.pack.tar.gz` | 456764 | `45e0150d528860bbc93e542575e8676ba7e187e35658075033662b81ff096086` |

`tactiq-altered-sets.py` builds the sets from one genuine, complete download
of the release and runs a checker over them. `make` signs its forged sets
with keys it generates on each run, so two runs give different forgeries.
The pack holds the exact sets the results in the rc14 errata were obtained
on, stored as the differences from the genuine release; `unpack` rebuilds
them byte for byte.

```
python3 tactiq-altered-sets.py list
python3 tactiq-altered-sets.py unpack tactiq-altered-sets-rc14.pack.tar.gz <rc14-download> sets
python3 tactiq-altered-sets.py run sets --kind l3 --reads tarball -- bash scripts/verify-l3-rc14-v2.sh {}
python3 tactiq-altered-sets.py run sets --kind release -- bash scripts/verify-release.sh --dir {} --identity https://github.com/revenue7-eng/tactiq-os/.github/workflows/release-sign.yml@refs/tags/v2.1.0-rc14
```

What the sets found in our checkers and how it was fixed is in
`docs/release-notes/v2.1.0-rc14-errata.md`.
