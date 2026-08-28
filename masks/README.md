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

`b1_dam` retains 100% of voxels (4096/4096): the archive genuinely has no background
in `SFalpha`/`SF2alpha`, and this matches qmrust's own comment on this dataset that the
comparison "holds over the whole image including the out-of-domain voxels where the
ratio exceeds 1" — a full mask is the honest answer here, not a misfire, so this does
not need re-investigating.

## Interior masks — cross-software comparison only

`masks/<model>_interior.nii.gz` is a **second** mask, written for derived models only:

| Model | Thresholded on | Otsu threshold | Retained |
|---|---|---|---|
| `b1_afi` | `AFIData1` | 148.545 | 103,286 / 360,448 (28.7%) |
| `mt_sat` | `PDw` | 201.752 | 588,562 / 1,572,864 (37.4%) |

It is Otsu's threshold on one input volume, ANDed with that model's mask above, so an
interior mask is always a strict **subset** of the mask the published numbers use.

**They are used only for cross-software comparison statistics.** The published
statistics, the drift history, and `voxel_sha256` all keep using `masks/<model>.nii.gz`
untouched, so adding these moved no number and no digest. The site carries both and says
which is which.

### Why a second mask at all

`masks/mt_sat.nii.gz` keeps 1,497,725 of 1,572,864 voxels (95.2%). It is a
finite-and-positive derivation and `MTw`/`PDw`/`T1w` are int16 scanner images, so
background noise is > 0 and survives. That near-background region is where the softwares
differ *by construction* rather than by fit: SCT clips `R1 < 0.01` to `T1 = 0`, qMRLab
leaves `R1 = 0` and produces `T1 = Inf`, hMRI clips R1 into `[0, 2]`. A headline number
computed there measures three background conventions. The interior mask is the region
where all three are actually fitting something.

The interior masks are spatially coherent, which is the check that they are anatomy and
not a noise cut: `mt_sat` is empty on the seven end slices and peaks at 57.6% mid-volume;
`b1_afi` runs 2.1% on its first slice, 0.5% on its last, and 49.3% at its widest.

### Why Otsu, and why not BET

Otsu is parameter-free, deterministic, and a dozen lines of numpy, so this directory's
standard survives — *a reviewer can rerun `derive_masks.py` and get the committed bytes
back*. Its bin count (256, the conventional resolution) is the method's only quantity,
and on these archives a bin is a handful of intensity counts, well under the noise floor
the split separates.

BET was considered and rejected. It needs FSL installed, its output moves with the FSL
version and with the `-f` parameter — either of which breaks byte-reproducibility — and
it could not become the general rule anyway: `qmt_spgr` is a single 88×128 slice, and
brain extraction on a 2D slice is not a thing. One derivation rule beats two.

### Which volume is thresholded, and why `b1_dam` has no interior mask

`scripts/derive_masks.py`'s `INTERIOR_FROM` names the volume per model rather than taking
the first entry of the input list, because which volume shows anatomy is a fact about the
contrast, not about list order.

For `mt_sat` that volume is **`PDw`, not `MTw`**. `MTw` is the saturated image, so the
tissue with the strongest MT effect is its dimmest: Otsu on `MTw` drops 152,804 voxels
whose median MTsat is 3.97 p.u. against 2.50 p.u. over the `PDw` interior. Those are the
white-matter voxels the model exists to measure, and cutting them would tilt every
cross-software comparison toward CSF and grey matter.

`b1_dam` deliberately gets **no** interior mask, recorded as `None` rather than by
omission. It is a single 64×64 slice of a phantom that fills the frame, so there is no
background to cut; and `SFalpha` is bright at the rim and dark through the middle, so
Otsu separates rim from centre and would keep an **annulus**, discarding the interior of
the object being measured. A model missing from `INTERIOR_FROM` entirely raises, so
"nobody decided yet" can never be mistaken for "decided against".
