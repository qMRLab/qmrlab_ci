function arr = qmrlab_ci_read_nii(path)
%QMRLAB_CI_READ_NII Read a NIfTI-1 volume in STORAGE order.
%
%   The harness owns this reader for the same reason it owns the writer. qMRLab's
%   load_nii_data reorients volumes according to the file's affine, and the flips it
%   applies differ per file (verified: MTw needs axis 1 flipped, AFIData1 needs axes 1
%   and 2). Worse, this benchmark runs 14 qMRLab versions whose reorientation rules may
%   themselves differ -- which would make "every target fits identical bytes" false while
%   every job still went green. Fits are voxelwise, so orientation is irrelevant to the
%   numbers; what matters is that input and output share one order.
    tmpdir = '';
    if endsWith(path, '.gz')
        tmpdir = tempname;
        mkdir(tmpdir);
        names = gunzip(path, tmpdir);
        p = names{1};
    else
        p = path;
    end
    % The temp directory must go whether we return normally or error out mid-read.
    cleaner = onCleanup(@() qmrlab_ci_rmtmp(tmpdir)); %#ok<*NASGU>

    % The returned fid is already open in the file's own byte order, so every fread
    % below inherits it and no endian argument has to be threaded through.
    fid = qmrlab_ci_open_nii(p, path);

    fseek(fid, 40, 'bof');
    dim = fread(fid, 8, 'int16=>double');
    fseek(fid, 70, 'bof');
    datatype = fread(fid, 1, 'int16=>double');
    fseek(fid, 108, 'bof');
    vox_offset = fread(fid, 1, 'float32=>double');
    scl = fread(fid, 2, 'float32=>double');   % slope at 112, intercept at 116

    switch datatype
        case 2,  fmt = 'uint8=>double';
        case 4,  fmt = 'int16=>double';
        case 8,  fmt = 'int32=>double';
        case 16, fmt = 'single=>double';
        case 64, fmt = 'double=>double';
        otherwise
            fclose(fid);
            error('qmrlab_ci:badNifti', '%s: unsupported NIfTI datatype %d', path, datatype);
    end

    dims = dim(2:1+dim(1))';
    fseek(fid, vox_offset, 'bof');
    raw = fread(fid, prod(dims), fmt);
    fclose(fid);
    if numel(raw) ~= prod(dims)
        error('qmrlab_ci:badNifti', '%s: file holds %d voxels, header declares %d', ...
              path, numel(raw), prod(dims));
    end

    % A zero slope means the intensity transform is UNSET and is skipped ENTIRELY,
    % intercept included. Applying the intercept anyway would multiply the data by zero,
    % which is the one case the spec explicitly forbids.
    if scl(1) ~= 0 && (scl(1) ~= 1 || scl(2) ~= 0)
        raw = scl(1) * raw + scl(2);
    end

    arr = reshape(raw, [dims 1 1]);
end
