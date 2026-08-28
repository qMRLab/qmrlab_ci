"""scripts/mat_to_nifti.py converts the .mat-only archives once, centrally (spec §6.2).

Everything here is synthetic: the archives are not in CI, and the properties that matter
— memory order, output dtype, stack order, byte reproducibility — are properties of the
converter and not of any particular volume.
"""
import gzip
import struct

import numpy as np
import pytest
import scipy.io

from harness.nifti import read_nifti
from scripts.derive_masks import write_mask_nifti
from scripts.mat_to_nifti import (
    MAT_INPUTS,
    STACK_ORDER,
    _undeclared,
    check_mask,
    load_mat,
    out_dtype,
    stack4d,
    write_nifti,
)


def _roundtrip(path):
    image = read_nifti(path)
    return image.values.reshape(image.shape, order="F"), image


def test_written_values_survive_the_round_trip_in_fortran_order(tmp_path):
    """The whole risk in this converter. MATLAB stores column-major and NIfTI serialises
    column-major, so reading one and writing the other in C order preserves the shape and
    every summary statistic while moving every voxel — a transposed input that fits, and
    publishes numbers, without anything raising."""
    array = np.arange(24, dtype=np.float32).reshape(2, 3, 4)
    path = tmp_path / "v.nii.gz"

    write_nifti(path, array)

    back, image = _roundtrip(path)
    assert image.shape == (2, 3, 4)
    np.testing.assert_array_equal(back, array)


def test_two_writes_of_the_same_array_are_byte_identical(tmp_path):
    """The one property the file exists to provide: a QUIT lane and an SCT lane fit the
    same bytes no matter when each was prepared. gzip stamps the current time into its
    header by default, which would break it silently — the content would still match."""
    array = np.arange(6, dtype=np.float32).reshape(2, 3)
    a, b = tmp_path / "a.nii.gz", tmp_path / "b.nii.gz"

    write_nifti(a, array)
    write_nifti(b, array)

    assert a.read_bytes() == b.read_bytes()


def test_the_gzip_header_carries_no_timestamp(tmp_path):
    """Asserted on the bytes as well as on a same-second rewrite, because two writes one
    second apart is exactly the case a same-process comparison cannot catch."""
    path = tmp_path / "v.nii.gz"

    write_nifti(path, np.zeros((2, 2), dtype=np.float32))

    assert struct.unpack_from("<I", path.read_bytes(), 4)[0] == 0


def test_a_float32_source_is_written_as_float32():
    assert out_dtype(np.float32, "x") == np.dtype("float32")


def test_a_float64_source_stays_float64():
    """Rounding it into float32 would move every fitted number of every lane that reads
    the file, while every checksum in the repo still matched."""
    assert out_dtype(np.float64, "x") == np.dtype("float64")


def test_narrow_integer_sources_widen_losslessly_to_float32():
    """int16 is the mtsat archive's storage type and uint8/int16 the masks'; the float32
    mantissa covers each of those ranges exactly, so the widening loses nothing."""
    for dtype in (np.int8, np.uint8, np.int16, np.uint16):
        assert out_dtype(dtype, "x") == np.dtype("float32")


def test_an_undeclared_source_dtype_raises_rather_than_rounding():
    """int32 does NOT fit exactly in float32, which is why it is absent from the table
    rather than mapped to it. An unconsidered type must stop the run, not lose precision
    on the way to four fitters."""
    with pytest.raises(ValueError, match="int32"):
        out_dtype(np.int32, "osf-data/x/Thing.mat")


def test_the_dtype_error_names_the_file(tmp_path):
    with pytest.raises(ValueError, match="Thing.mat"):
        out_dtype(np.complex64, "osf-data/x/Thing.mat")


def test_the_nifti_datatype_code_matches_the_array(tmp_path):
    """16/64 are the NIfTI-1 codes for float32/float64; a reader trusts the code, not the
    file size, so a mismatch reads the body at the wrong stride."""
    single, double = tmp_path / "a.nii.gz", tmp_path / "b.nii.gz"

    write_nifti(single, np.zeros((2, 2), dtype=np.float32))
    write_nifti(double, np.zeros((2, 2), dtype=np.float64))

    assert read_nifti(single).datatype == 16
    assert read_nifti(double).datatype == 64


def test_a_one_dimensional_array_is_refused(tmp_path):
    """These archives are 2-D through 4-D; anything else means the array was reshaped by
    mistake somewhere upstream, and a 1-D NIfTI would be accepted by the reader."""
    with pytest.raises(ValueError, match="1-D"):
        write_nifti(tmp_path / "v.nii.gz", np.zeros(4, dtype=np.float32))


def test_a_five_dimensional_array_is_refused(tmp_path):
    with pytest.raises(ValueError, match="5-D"):
        write_nifti(tmp_path / "v.nii.gz", np.zeros((1, 1, 1, 1, 1), dtype=np.float32))


def test_voxel_sizes_are_written_because_two_other_softwares_read_them(tmp_path):
    """derive_masks.py leaves pixdim zero, which is harmless for a file only this repo
    indexes. These files are opened by QUIT and SCT, where a zero voxel size is not a
    neutral 'unset' — it propagates into the affine."""
    path = tmp_path / "v.nii.gz"

    write_nifti(path, np.zeros((2, 2), dtype=np.float32))

    pixdim = struct.unpack_from("<8f", gzip.decompress(path.read_bytes()), 76)
    assert pixdim[1:4] == (1.0, 1.0, 1.0)


def test_load_mat_returns_the_single_variable_and_its_name(tmp_path):
    path = tmp_path / "MTon.mat"
    scipy.io.savemat(path, {"MTon": np.arange(6, dtype=np.float32).reshape(2, 3)})

    name, array = load_mat(path)

    assert name == "MTon"
    assert array.shape == (2, 3)


def test_load_mat_refuses_a_file_with_two_variables(tmp_path):
    """derive_masks.py takes the first variable it finds, which is right for a mask it
    thresholds on the spot. Here the array becomes a fit input for three other softwares,
    and picking one of several by dict order would make which volume QUIT fits depend on
    scipy's insertion order."""
    path = tmp_path / "Both.mat"
    scipy.io.savemat(path, {"MTon": np.zeros((2, 2)), "MToff": np.ones((2, 2))})

    with pytest.raises(ValueError, match="exactly one variable"):
        load_mat(path)


def test_a_stack_keeps_the_declared_volume_order():
    """A swapped pair does not fail — it fits the reciprocal, or the negative, of the
    intended quantity and reports it as a number."""
    first = np.full((2, 2, 2), 1.0, dtype=np.float32)
    second = np.full((2, 2, 2), 2.0, dtype=np.float32)

    stacked = stack4d([first, second], ("MTon", "MToff"))

    assert stacked.shape == (2, 2, 2, 2)
    np.testing.assert_array_equal(stacked[..., 0], first)
    np.testing.assert_array_equal(stacked[..., 1], second)


def test_single_slice_volumes_get_their_slice_axis_back_before_stacking():
    """b1_dam and mtr's single-slice archives store 2-D. Stacking them as-is would put the
    volume axis at index 2 here and at index 3 in the stacks qmrust already fits."""
    stacked = stack4d(
        [np.zeros((4, 4), dtype=np.float32), np.ones((4, 4), dtype=np.float32)],
        ("SFalpha", "SF2alpha"),
    )

    assert stacked.shape == (4, 4, 1, 2)


def test_stacking_volumes_of_different_shapes_raises(tmp_path):
    """numpy would broadcast, producing a plausible 4-D volume that no longer holds the
    acquisition it claims to."""
    with pytest.raises(ValueError, match="PDw"):
        stack4d(
            [np.zeros((2, 2, 2), dtype=np.float32), np.zeros((2, 2, 3), dtype=np.float32)],
            ("MTw", "PDw"),
        )


def test_stacking_volumes_of_different_dtypes_raises():
    """numpy would promote silently, so a stack's dtype would depend on which member
    happened to be widest instead of on a declaration."""
    with pytest.raises(ValueError, match="MToff"):
        stack4d(
            [np.zeros((2, 2, 2), dtype=np.float32), np.zeros((2, 2, 2), dtype=np.float64)],
            ("MTon", "MToff"),
        )


def test_the_declared_stack_orders_are_the_ones_qmrust_already_fits():
    """Pinned rather than inferred. These four orders are established in
    targets/qmrust@main/run.sh::prepare_input() against each model's Rust source, and a
    reordering here would be invisible: every model would still produce every map."""
    assert STACK_ORDER == {
        "b1_afi": ("b1_afi", ("AFIData1", "AFIData2")),
        "b1_dam": ("b1_dam", ("SFalpha", "SF2alpha")),
        "mt_sat": ("mtsat", ("MTw", "PDw", "T1w")),
        "mt_ratio": ("mtr", ("MTon", "MToff")),
    }


def test_every_stacked_model_draws_from_a_dataset_the_converter_or_the_archive_has():
    """mt_ratio's members are .mat and the other three models' are .nii.gz — the stacking
    step straddles the split this script exists for, so its datasets are not all in
    MAT_INPUTS and must not be assumed to be."""
    assert STACK_ORDER["mt_ratio"][0] in MAT_INPUTS


def test_an_extra_mat_in_an_archive_is_reported_rather_than_converted(tmp_path):
    """A re-uploaded archive that quietly gained a file must not quietly gain a converted
    input: this tree is what the non-MATLAB lanes fit."""
    (tmp_path / "mtr").mkdir()
    for name in ("MTon.mat", "MToff.mat", "Mask.mat", "Surprise.mat"):
        (tmp_path / "mtr" / name).write_bytes(b"")

    assert _undeclared(tmp_path, "mtr", MAT_INPUTS["mtr"]) == ["Surprise.mat"]


def test_the_archives_own_fitted_output_is_not_mistaken_for_an_input(tmp_path):
    """FitResults/ holds qMRLab's fitted maps under names identical to the inputs."""
    (tmp_path / "mtr" / "FitResults").mkdir(parents=True)
    (tmp_path / "mtr" / "FitResults" / "FitResults.mat").write_bytes(b"")
    for name in MAT_INPUTS["mtr"]:
        (tmp_path / "mtr" / name).write_bytes(b"")

    assert _undeclared(tmp_path, "mtr", MAT_INPUTS["mtr"]) == []


def test_a_converted_mask_matching_the_committed_one_reports_its_voxel_count(tmp_path):
    mask = np.array([[1.0, 0.0, 3.0], [0.0, 2.0, 0.0]], dtype=np.float32)
    committed = tmp_path / "m.nii.gz"
    write_mask_nifti(committed, (mask.ravel(order="F") > 0).astype(np.uint8), mask.shape)

    assert check_mask(mask, committed) == 3


def test_a_transposed_mask_is_caught_even_though_its_voxel_count_is_right(tmp_path):
    """The reason check_mask compares voxels instead of counting them. Reading a MATLAB
    array in C order leaves the number of nonzero voxels exactly as it was and puts every
    one of them somewhere else, so a count check would pass on a silently transposed tree
    while every downstream statistic was computed over the wrong voxels."""
    mask = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 1.0]], dtype=np.float32)
    committed = tmp_path / "m.nii.gz"
    write_mask_nifti(committed, (mask.ravel(order="F") > 0).astype(np.uint8), mask.shape)
    wrong_order = mask.ravel(order="C").reshape(mask.shape, order="F")

    assert int(np.count_nonzero(wrong_order)) == int(np.count_nonzero(mask))
    with pytest.raises(ValueError, match="wrong memory order"):
        check_mask(wrong_order, committed)


def test_a_mask_of_the_wrong_shape_names_both_shapes(tmp_path):
    mask = np.ones((2, 3), dtype=np.float32)
    committed = tmp_path / "m.nii.gz"
    write_mask_nifti(committed, np.ones(6, dtype=np.uint8), (2, 3))

    with pytest.raises(ValueError, match=r"\(3, 2\)"):
        check_mask(np.ones((3, 2), dtype=np.float32), committed)
