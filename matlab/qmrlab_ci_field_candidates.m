function fields = qmrlab_ci_field_candidates(modelId, mapName)
%QMRLAB_CI_FIELD_CANDIDATES FitResults field names that may hold a canonical map.
%
%   Canonical map names are the benchmark's vocabulary; qMRLab's FitResults field
%   names are qMRLab's, and they differ and drift across versions. Candidates are
%   tried IN ORDER, so raw comes first: the filtered variant is FilterClass
%   post-processing rather than the fit, and comparing it against another software's
%   fit would be comparing different quantities. Verified on v3.0.0 -- B1map_raw
%   matches the archive's own reference at r=1.0, B1map_filtered at r=0.48.
%
%   mt_sat/MTsat added after the same v3.0.0 sweep found FitData returns a field
%   literally named MTSAT (all-caps) for this model, not the canonical MTsat -- a
%   casing drift, not a raw/filtered distinction, so the actual field is tried first
%   with the canonical spelling kept as a fallback for any version that uses it.
    key = [modelId '/' mapName];
    switch key
        case {'b1_dam/B1map', 'b1_afi/B1map'}
            fields = {'B1map_raw', 'B1map'};
        case 'mt_sat/MTsat'
            fields = {'MTSAT', 'MTsat'};
        otherwise
            fields = {mapName};
    end
end
