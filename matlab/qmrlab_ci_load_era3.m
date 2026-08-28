function [data, Model] = qmrlab_ci_load_era3(dataRoot, modelId)
%QMRLAB_CI_LOAD_ERA3 Assemble one model's inputs from the canonical input tree.
%
%   Each model object's default Prot already matches its demo dataset -- that is what
%   makes qMRgenBatch demos work -- so the protocol is not overridden here. If a fit
%   disagrees with the FitResults shipped in the archive, that assumption is the first
%   thing to check.
    switch modelId
        case 'inversion_recovery'
            Model = inversion_recovery;
            data.IRData = qmrlab_ci_load_any(dataRoot, 'ir', 'IRData.mat');
            data.Mask   = qmrlab_ci_load_any(dataRoot, 'ir', 'Mask.mat');
        case {'qmt_spgr', 'qmt_spgr_ramani'}
            Model = qmt_spgr;
            % Two comparison streams through ONE qMRLab class: the sub-model is a
            % plain options field named exactly 'Model'. qmt_spgr is left alone rather
            % than assigned 'SledPikeRP' explicitly -- button2opts takes the FIRST
            % entry of qmt_spgr.m's {'SledPikeRP','SledPikeCW','Yarnykh','Ramani'} as
            % the default, so never touching the field is what makes that stream the
            % version's OWN default rather than a choice this benchmark imposed, and
            % the difference between those two is what the benchmark measures.
            %
            % st/lb/ub/fx and fittingconstraints_* are likewise left at each version's
            % defaults for both streams; see qmrlab_ci_load_era2.m for the two spreads
            % that produces, which are real per-version drift and not a harness bug.
            if strcmp(modelId, 'qmt_spgr_ramani')
                Model.options.Model = 'Ramani';
            end
            data.MTdata = qmrlab_ci_load_any(dataRoot, 'qmt', 'MTdata.mat');
            data.Mask   = qmrlab_ci_load_any(dataRoot, 'qmt', 'Mask.mat');
            data.R1map  = qmrlab_ci_load_any(dataRoot, 'qmt', 'R1map.mat');
            data.B1map  = qmrlab_ci_load_any(dataRoot, 'qmt', 'B1map.mat');
            data.B0map  = qmrlab_ci_load_any(dataRoot, 'qmt', 'B0map.mat');
        case 'vfa_t1'
            Model = vfa_t1;
            data.VFAData = qmrlab_ci_load_any(dataRoot, 'vfa_t1', 'VFAData.nii.gz');
            data.Mask    = qmrlab_ci_load_any(dataRoot, 'vfa_t1', 'Mask.nii.gz');
            data.B1map   = qmrlab_ci_load_any(dataRoot, 'vfa_t1', 'B1map.nii.gz');
        case 'mono_t2'
            Model = mono_t2;
            data.SEdata = qmrlab_ci_load_any(dataRoot, 'mono_t2', 'SEdata.nii.gz');
            data.Mask   = qmrlab_ci_load_any(dataRoot, 'mono_t2', 'Mask.nii.gz');
        case 'mt_ratio'
            Model = mt_ratio;
            data.MTon  = qmrlab_ci_load_any(dataRoot, 'mtr', 'MTon.mat');
            data.MToff = qmrlab_ci_load_any(dataRoot, 'mtr', 'MToff.mat');
            data.Mask  = qmrlab_ci_load_any(dataRoot, 'mtr', 'Mask.mat');
        case 'mt_sat'
            Model = mt_sat;
            data.MTw = qmrlab_ci_load_any(dataRoot, 'mtsat', 'MTw.nii.gz');
            data.PDw = qmrlab_ci_load_any(dataRoot, 'mtsat', 'PDw.nii.gz');
            data.T1w = qmrlab_ci_load_any(dataRoot, 'mtsat', 'T1w.nii.gz');
        case 'b1_dam'
            Model = b1_dam;
            data.SFalpha  = qmrlab_ci_load_any(dataRoot, 'b1_dam', 'SFalpha.nii.gz');
            data.SF2alpha = qmrlab_ci_load_any(dataRoot, 'b1_dam', 'SF2alpha.nii.gz');
        case 'b1_afi'
            Model = b1_afi;
            data.AFIData1 = qmrlab_ci_load_any(dataRoot, 'b1_afi', 'AFIData1.nii.gz');
            data.AFIData2 = qmrlab_ci_load_any(dataRoot, 'b1_afi', 'AFIData2.nii.gz');
        otherwise
            error('qmrlab_ci:unknownModel', 'no era-3 loader for %s', modelId);
    end
end
