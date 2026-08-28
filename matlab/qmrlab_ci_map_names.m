function names = qmrlab_ci_map_names(modelId, era)
%QMRLAB_CI_MAP_NAMES Canonical output maps per model, matching models/<id>.yml.
%
%   ERA narrows the list rather than widening it: v2.0.5's MTSAT class
%   (Models/Myelin_Imaging/MTSAT.m) only ever computes FitResult.MTSAT -- there is
%   no code path there for T1 or MTR at all, unlike v3.0.0's mt_sat.m. Declaring
%   that gap here turns a real era capability difference into a hole in the matrix
%   (spec Sec 2.4: availability is declared) instead of a loud, spurious
%   missingOutput failure. Every other model/era combination gets the full
%   canonical list, unchanged.
    switch modelId
        % Both qMT streams produce the same six xnames -- SledPikeRP and Ramani are
        % two ways of estimating one parameter set, not two parameter sets.
        case {'qmt_spgr','qmt_spgr_ramani'}
            names = {'F','kr','R1f','R1r','T2f','T2r'};
        case 'inversion_recovery'; names = {'T1'};
        case 'vfa_t1';             names = {'T1','M0'};
        case 'b1_dam';             names = {'B1map'};
        case 'b1_afi';             names = {'B1map'};
        case 'mono_t2';            names = {'T2','M0'};
        case 'mt_ratio';           names = {'MTR'};
        case 'mt_sat'
            if era == 2
                names = {'MTsat'};
            else
                names = {'MTsat','T1','MTR'};
            end
        otherwise; error('qmrlab_ci:unknownModel', 'no map list for %s', modelId);
    end
end
