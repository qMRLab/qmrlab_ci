function arr = qmrlab_ci_load_any(dataRoot, dataset, name)
%QMRLAB_CI_LOAD_ANY Find NAME anywhere under DATAROOT/DATASET and load it.
%   Archive layouts differ (some nest a folder, some do not), so the file is located
%   rather than assumed -- the same reason qmrust's ci/datasets.sh has a `locate`.
    hits = dir(fullfile(dataRoot, dataset, '**', name));

    % Deliberately blind to FitResults/: that directory holds qMRLab's own fitted output,
    % and several archives ship files there under names identical to the inputs, so a hit
    % there would mean qMRLab was fitted against its own published result -- silently.
    % dir('**') returns the FitResults copy FIRST, so ordering is no defence, and no
    % ordering rule here is right by construction: ambiguity raises rather than picks.
    % Mirrors scripts/derive_masks.py's _find, because two locators walking the same
    % archive tree must not disagree about which file is the input.
    keep = true(1, numel(hits));
    for ii = 1:numel(hits)
        parts = regexp(hits(ii).folder, '[/\\]', 'split');
        keep(ii) = ~any(strcmp(parts, 'FitResults'));
    end
    hits = hits(keep);

    if isempty(hits)
        error('qmrlab_ci:missingInput', '%s not found under %s/%s (excluding FitResults/)', ...
              name, dataRoot, dataset);
    end
    if numel(hits) > 1
        paths = arrayfun(@(h) fullfile(h.folder, h.name), hits, 'UniformOutput', false);
        error('qmrlab_ci:ambiguousInput', '%s is ambiguous under %s/%s: %s', ...
              name, dataRoot, dataset, strjoin(paths(:)', ', '));
    end
    p = fullfile(hits(1).folder, hits(1).name);
    if endsWith(name, '.mat')
        s = load(p);
        f = fieldnames(s);
        % double(), matching the NIfTI branch. qMRLab's voxelwise fits fail at EVERY
        % voxel on non-double input, and the failure is close to invisible: the error
        % reporter (cprintf) falls over while reporting it, so what surfaces is a crash
        % in a printing utility rather than a type problem in the data.
        arr = double(s.(f{1}));
    else
        % NOT load_nii_data: it reorients each volume by that file's affine, so two
        % inputs to one fit can arrive in different storage orders -- and the rule
        % may itself differ across the 14 qMRLab versions this benchmark measures.
        arr = qmrlab_ci_read_nii(p);
    end
end
