function qmrlab_ci_record(outPath, record)
%QMRLAB_CI_RECORD Write one adapter record as JSON.
%
%   Adapters report facts only: status, timing, units, paths. Statistics and hashes
%   are computed once in the Python harness, so that a difference between two targets
%   is a difference between the softwares rather than between two implementations of
%   the same statistic.
    [outDir, ~, ~] = fileparts(outPath);
    if ~isempty(outDir) && ~exist(outDir, 'dir'), mkdir(outDir); end

    % jsonencode maps a 1xN cell of structs to a JSON array, which is what the
    % schema expects for `maps`. A bare struct array would encode as an object.
    fid = fopen(outPath, 'w');
    fwrite(fid, jsonencode(record));
    fclose(fid);
end
