# Repo-owned masks

Every software and version is scored over these exact regions, so a difference in a
masked mean isolates the fit rather than the masking.

Regenerate with:

    python -m scripts.fetch_data --out osf-data
    python -m scripts.derive_masks --data osf-data

The committed bytes are that script's output. Two rules:

| Model | Rule |
|---|---|
| `inversion_recovery` | `Mask.mat` shipped in the `ir` archive |
| `qmt_spgr` | `Mask.mat` shipped in the `qmt` archive |
| `mt_ratio` | `Mask.mat` shipped in the `mtr` archive |
| `mono_t2` | `Mask.nii.gz` shipped in the `mono_t2` archive |
| `vfa_t1` | `Mask.nii.gz` shipped in the `vfa_t1` archive |
| `b1_dam` | Voxels finite and > 0 across `SFalpha` and `SF2alpha` |
| `b1_afi` | Voxels finite and > 0 across `AFIData1` and `AFIData2` |
| `mt_sat` | Voxels finite and > 0 across `MTw`, `PDw`, and `T1w` |

The three derived masks exist because those archives ship no mask. The rule is the one
qmrust's `ci/compare_maps.py` applies implicitly when it restricts to finite, positive
voxels — made explicit so it is applied identically to every target and can be reviewed.
