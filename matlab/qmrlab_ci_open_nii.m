function [fid, endian] = qmrlab_ci_open_nii(p, origPath)
%QMRLAB_CI_OPEN_NII Open a NIfTI-1 file, detecting byte order from sizeof_hdr.
    endian = 'l';
    fid = fopen(p, 'r', 'l');
    if fid < 0
        error('qmrlab_ci:badNifti', '%s: cannot open', origPath);
    end
    % A truncated file returns [] here, and [] ~= 348 is empty, which `if` treats as
    % false -- so the read is checked for a scalar before it is compared.
    hdrSize = fread(fid, 1, 'int32=>double');
    if ~isscalar(hdrSize) || hdrSize ~= 348
        fclose(fid);
        endian = 'b';
        fid = fopen(p, 'r', 'b');
        hdrSize = fread(fid, 1, 'int32=>double');
        if ~isscalar(hdrSize) || hdrSize ~= 348
            fclose(fid);
            error('qmrlab_ci:badNifti', '%s: sizeof_hdr is not 348 in either byte order', origPath);
        end
    end
end
