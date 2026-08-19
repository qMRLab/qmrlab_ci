function qmrlab_ci_write_nii(outPath, data)
%QMRLAB_CI_WRITE_NII Write DATA as a float64 NIfTI-1 (.nii.gz).
%
%   Harness-owned rather than delegated to each qMRLab version's own save routine.
%   The benchmark hashes voxel values to detect when two targets produce identical
%   fits; if every version serialized differently, that hash would partly measure the
%   serializer. One writer for all MATLAB targets keeps it a property of the fit.
    data = double(data);
    dims = size(data);
    while numel(dims) > 2 && dims(end) == 1
        dims(end) = [];
    end
    ndim = numel(dims);

    hdr = zeros(1, 348, 'uint8');
    hdr(1:4)     = typecast(int32(348), 'uint8');
    hdr(41:56)   = typecast(int16([ndim, dims, ones(1, 7 - ndim)]), 'uint8');
    hdr(71:72)   = typecast(int16(64), 'uint8');     % datatype: float64
    hdr(73:74)   = typecast(int16(64), 'uint8');     % bitpix
    hdr(109:112) = typecast(single(352), 'uint8');   % vox_offset
    hdr(113:116) = typecast(single(1), 'uint8');     % scl_slope
    hdr(117:120) = typecast(single(0), 'uint8');     % scl_inter
    hdr(345:348) = uint8(['n+1', 0]);                % magic

    % fileparts('T1.nii.gz') returns base 'T1.nii' and ext '.gz', so BASE already
    % carries the .nii -- appending another would write T1.nii.nii and gzip would
    % produce T1.nii.nii.gz, a path no record points at.
    [outDir, base, ~] = fileparts(outPath);
    if ~isempty(outDir) && ~exist(outDir, 'dir'), mkdir(outDir); end
    plain = fullfile(outDir, base);

    fid = fopen(plain, 'w', 'l');
    fwrite(fid, hdr, 'uint8');
    fwrite(fid, zeros(1, 4, 'uint8'), 'uint8');
    fwrite(fid, data(:), 'double');
    fclose(fid);

    gzip(plain);
    delete(plain);
end
