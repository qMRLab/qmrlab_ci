function arr = qmrlab_ci_load_any(dataRoot, dataset, name)
%QMRLAB_CI_LOAD_ANY Find NAME anywhere under DATAROOT/DATASET and load it.
%   Archive layouts differ (some nest a folder, some do not), so the file is located
%   rather than assumed -- the same reason qmrust's ci/datasets.sh has a `locate`.
    hits = dir(fullfile(dataRoot, dataset, '**', name));
    if isempty(hits)
        error('qmrlab_ci:missingInput', '%s not found under %s/%s', name, dataRoot, dataset);
    end
    p = fullfile(hits(1).folder, hits(1).name);
    if endsWith(name, '.mat')
        s = load(p);
        f = fieldnames(s);
        arr = s.(f{1});
    else
        arr = double(load_nii_data(p));
    end
end
