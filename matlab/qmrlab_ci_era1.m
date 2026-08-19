function qmrlab_ci_era1(dataRoot, outRoot, targetId, qmrlabVersion, matlabRelease, models, repeatsJson)
%QMRLAB_CI_ERA1 Drive qMTLab V1 headless.
%
%   V1 predates the model-object API: FitData takes (data, Prot, FitOpt, Method, wait)
%   rather than a model that carries all three. It contributes one model, qmt_spgr.
    repeats = jsondecode(repeatsJson);
    n = qmrlab_ci_repeats_for(repeats, 'qmt_spgr');
    % MODELS is accepted so all three drivers share one call signature. V1 has exactly
    % one model, so anything else means target.yml and this driver have drifted apart.
    if ~isequal(models, {'qmt_spgr'})
        error('qmrlab_ci:unexpectedModels', ...
              'V1 supports only qmt_spgr; target.yml declares %d model(s)', numel(models));
    end
    env = struct( ...
        'matlab_release', matlabRelease, ...
        'runner_os', getenv('RUNNER_OS'), ...
        'harness_commit', getenv('GITHUB_SHA'), ...
        'run_started_utc', getenv('QMRLAB_CI_RUN_STARTED'));

    record = struct('target', targetId, 'software', 'qmrlab', ...
                    'version', qmrlabVersion, 'model', 'qmt_spgr', 'status', 'ok', ...
                    'environment', env, 'timing', struct(), 'maps', {{}});
    try
        [Prot, FitOpt] = qmrlab_ci_era1_protocol();

        data.MTdata = qmrlab_ci_load_any(dataRoot, 'qmt', 'MTdata.mat');
        data.Mask   = qmrlab_ci_load_any(dataRoot, 'qmt', 'Mask.mat');
        data.R1map  = qmrlab_ci_load_any(dataRoot, 'qmt', 'R1map.mat');
        data.B1map  = qmrlab_ci_load_any(dataRoot, 'qmt', 'B1map.mat');
        data.B0map  = qmrlab_ci_load_any(dataRoot, 'qmt', 'B0map.mat');

        if size(data.MTdata, ndims(data.MTdata)) ~= numel(Prot.Angles)
            error('qmrlab_ci:protocolMismatch', ...
                  'MTdata has %d points, protocol declares %d', ...
                  size(data.MTdata, ndims(data.MTdata)), numel(Prot.Angles));
        end

        [times, Fit] = qmrlab_ci_era1_run_fits(data, Prot, FitOpt, n);

        % V1 returns F, kf, kr, R1f, R1r, T2f, T2r, resnorm -- the same names later
        % versions produce. Resolved through qmrlab_ci_field_candidates rather than
        % assumed, so a surprise fails loudly instead of silently writing the wrong map.
        maps = {};
        resolved = {};
        names = qmrlab_ci_map_names('qmt_spgr');
        for jj = 1:numel(names)
            nm = names{jj};
            cands = qmrlab_ci_field_candidates('qmt_spgr', nm);
            src = '';
            for kk = 1:numel(cands)
                if isfield(Fit, cands{kk}), src = cands{kk}; break; end
            end
            if isempty(src)
                error('qmrlab_ci:missingOutput', ...
                      'qmt_spgr: none of {%s} present in Fit for map %s; Fit has {%s}', ...
                      strjoin(cands, ', '), nm, strjoin(fieldnames(Fit)', ', '));
            end
            if ~strcmp(src, nm)
                fprintf('  qmt_spgr/%s <- Fit.%s\n', nm, src);
            end
            resolved{end+1} = src;  %#ok<AGROW>
            rel = fullfile('maps', 'qmt_spgr', [nm '.nii.gz']);
            qmrlab_ci_write_nii(fullfile(outRoot, rel), Fit.(src));
            maps{end+1} = struct('name', nm, ...
                                 'unit', qmrlab_ci_unit_for('qmt_spgr', nm), ...
                                 'path', strrep(rel, '\', '/'));  %#ok<AGROW>
        end

        % Falls back to the size of the first map ACTUALLY produced, never the
        % canonical name, matching era 3's fix for the same fallback.
        if isfield(data, 'Mask') && ~isempty(data.Mask)
            nVox = nnz(data.Mask);
        else
            nVox = numel(Fit.(resolved{1}));
        end

        % jsonencode() writes a 1-element numeric array as a bare scalar, which
        % violates the record schema (repeats must equal numel(fit_seconds)). A cell
        % array always encodes as a JSON array, so the single-repeat case -- which is
        % the CONFIGURED case for qmt_spgr -- round-trips correctly.
        record.timing = struct('repeats', n, 'n_voxels_fitted', nVox);
        record.timing.fit_seconds = num2cell(times);
        record.maps = maps;
    catch err
        record.status = 'failed';
        record.error = sprintf('%s: %s', err.identifier, err.message);
        record.timing = struct();
        record.maps = {};
    end
    qmrlab_ci_record(fullfile(outRoot, 'records', 'qmt_spgr.json'), record);
    fprintf('%s / qmt_spgr: %s\n', targetId, record.status);
end

function [times, Fit] = qmrlab_ci_era1_run_fits(data, Prot, FitOpt, n)
%QMRLAB_CI_ERA1_RUN_FITS Repeat V1's FitData from an isolated temp directory.
%
%   V1's FitData writes FitTempResults.mat into the CURRENT directory every 20
%   voxels (Common/FitData.m) -- there is no argument to redirect it, and
%   in CI the current directory is the checkout, so left alone it litters the repo
%   and could end up inside an uploaded results artifact. Running from a throwaway
%   temp directory keeps it out of the checkout entirely; onCleanup restores the
%   caller's directory and deletes the temp one on every exit path, including a fit
%   that throws mid-loop, so one failed repeat cannot strand later models in the
%   wrong directory.
    origDir = pwd;
    tmpdir = tempname;
    mkdir(tmpdir);
    cd(tmpdir);
    cleaner = onCleanup(@() qmrlab_ci_era1_restore(origDir, tmpdir));

    times = zeros(1, n);
    for r = 1:n
        t0 = tic;
        Fit = FitData(data, Prot, FitOpt, 'SPGR', 0);
        times(r) = toc(t0);
    end
end

function qmrlab_ci_era1_restore(origDir, tmpdir)
%QMRLAB_CI_ERA1_RESTORE Return to ORIGDIR and remove TMPDIR. Runs on every exit path.
    cd(origDir);
    qmrlab_ci_rmtmp(tmpdir);
end
