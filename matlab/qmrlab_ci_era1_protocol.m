function [Prot, FitOpt] = qmrlab_ci_era1_protocol(modelId)
%QMRLAB_CI_ERA1_PROTOCOL The canonical qMT protocol, in V1's struct shape.
%
%   MODELID selects the sub-model, and nothing else: 'qmt_spgr' fits SledPikeRP and
%   'qmt_spgr_ramani' fits Ramani over an otherwise IDENTICAL Prot and FitOpt. Keeping
%   the two streams to a single differing field is the whole point -- any other
%   divergence here would land in the cross-software comparison as if it were a
%   sub-model effect.
%
%   Transcribed from qMRLab v3.0.0 src/Models/Magnetization_transfer/qmt_spgr.m --
%   its default Prot.MTdata.Mat, Prot.TimingTable.Mat, and buttons defaults -- because
%   the benchmark only means anything if V1 is asked the same question as every other
%   target. V1's own SPGR/Parameters/DefaultProt.mat is NOT used: it declares 15
%   measurement points for a dataset that has 10, plus a different TR and model.
%
%   The field is FitOpt.model, lowercase -- V1's own spelling. Eras 2 and 3 select the
%   same thing through Model.options.Model, capitalised, on a model object V1 predates.
%
%   qmt_spgr's 'SledPikeRP' is not an arbitrary pick: button2opts takes the FIRST entry
%   of qmt_spgr.m's Model cell array {'SledPikeRP','SledPikeCW','Yarnykh','Ramani'} as
%   the default -- verified live: qmt_spgr().GetFitOpt().model == 'SledPikeRP' on the
%   v3.0.0 checkout -- so it is what every era-2 and era-3 target fits by never touching
%   the field, and what the qmt archive's own FitResults were computed with. An earlier
%   round of this file used 'Ramani' for the qmt_spgr stream (taken from qmrust's recipe
%   filename, not from qMRLab itself); that mismatch, not version drift, was why the
%   V1-vs-v3.0.0 F-map agreement was only r=0.9466. Ramani is now a SEPARATE stream,
%   which is the honest way to compare it -- not a substitution inside this one.
%
%   CAVEAT for the Ramani stream on V1 (spec 6.3): of the 14 qMRLab targets, V1 alone
%   ignores the B1 map in its Ramani fit and V1 alone lacks the max(0.1, R1obs) floor
%   later versions apply to the R1map. data.B1map is still passed below, because V1's
%   own code is what drops it and correcting for that here would stop measuring V1.
%   Expect V1's Ramani F map to sit apart from the other 13 for a reason that is NOT
%   version drift in the estimator. Also stated in models/qmt_spgr_ramani.yml.
%
%   If V1's numbers look wrong, this function is the first suspect.

    % Ten (angle, offset) pairs, in acquisition order.
    Prot.Angles  = [142; 426; 142; 426; 142; 426; 142; 426; 142; 426];
    Prot.Offsets = [443; 443; 1088; 1088; 2732; 2732; 6862; 6862; 17235; 17235];

    % Timing, seconds. TR is the sum of the other four, which is the invariant
    % qmt_spgr.m re-imposes in UpdateFields.
    Prot.Tm = 0.0102;   % MT pulse duration
    Prot.Ts = 0.0030;   % free precession, MT pulse -> excitation
    Prot.Tp = 0.0018;   % excitation pulse duration
    Prot.Tr = 0.0100;   % free precession after excitation
    Prot.TR = Prot.Tm + Prot.Ts + Prot.Tp + Prot.Tr;   % 0.0250

    Prot.Alpha  = 7;    % read pulse alpha
    Prot.Npulse = 600;  % NOT V1's default of 100 -- modern qMRLab uses 600
    Prot.MTpulse.shape  = 'gausshann';
    Prot.MTpulse.opt.bw = 200;
    Prot.MTpulse.Npulse = 600;
    Prot.Method   = 'SPGR';
    Prot.FileType = 'Protocol';

    FitOpt.names = {'F', 'kr', 'R1f', 'R1r', 'T2f', 'T2r'};
    FitOpt.st = [0.16,   30,      1,    1,    0.03,   1.3e-05];
    FitOpt.lb = [0.0001, 0.0001,  0.05, 0.05, 0.003,  3.0e-06];
    FitOpt.ub = [0.5,    100,     5,    5,    0.5,    5.0e-05];
    FitOpt.fx = [0,      0,       1,    1,    0,      0];

    % The one field the two streams differ in. An unhandled id raises rather than
    % falling through to a default, matching the era-2 and era-3 loaders: a target.yml
    % that has drifted from this driver must fail loudly, never fit the wrong sub-model
    % under the other one's name.
    switch modelId
        case 'qmt_spgr';        FitOpt.model = 'SledPikeRP';
        case 'qmt_spgr_ramani'; FitOpt.model = 'Ramani';
        otherwise
            error('qmrlab_ci:unknownModel', 'no era-1 protocol for %s', modelId);
    end

    FitOpt.lineshape = 'SuperLorentzian';
    FitOpt.R1map     = 1;   % use the R1map to constrain R1f (why fx(3) is 1)
    FitOpt.R1reqR1f  = 0;   % do NOT fix R1r = R1f
    FitOpt.FixR1fT2f = 0;
    FitOpt.FixR1fT2fValue = 0.055;
    FitOpt.FileType = 'FitOpt';

    % Loaded for BOTH streams even though only SledPikeRP reads it, so that the two
    % FitOpt structs differ in exactly the one field set above. Ramani's fit function
    % never consults SfTable, so carrying it costs one file read and buys the guarantee
    % that nothing else varies between the streams.
    %
    % SledPikeRP (unlike Ramani) needs a precomputed Sf lookup table: SPGR_Srp_fun
    % calls GetSf(Angles, Offsets, T2f, FitOpt.SfTable), which interp3()s over a
    % (angle, offset, T2f) grid. V1 ships Sf_gh10240bw200.mat under
    % SPGR/Parameters/ -- found via the MATLAB path once qMRLab V1 is on it, same as
    % every other V1 function this driver calls without a full path. It is built for
    % a gausshann pulse with Trf=0.0102s and bandwidth=200Hz, which is EXACTLY this
    % protocol's MT pulse (Prot.Tm and Prot.MTpulse.opt.bw above): Sf depends only on
    % the pulse shape, not on which specific angles a protocol happens to acquire.
    % Verified live: its grid spans angles 0-1500deg (26 points), offsets ~10Hz-316kHz
    % (46 points), and T2f 0.001-1.0s (22 points) -- comfortably covering this
    % protocol's 142/426deg angles, 443-17235Hz offsets, and the fit's T2f search
    % range [0.003, 0.5], so GetSf's interp3 should not need its NaN/computeSf
    % fallback. It is also byte-identical to the SfTable V1's own
    % SPGR/Parameters/DefaultFitOpt.mat carries (verified with isequal on angles,
    % offsets and values) -- V1's own Yarnykh default reuses this exact file, this
    % protocol reuses it for SledPikeRP for the same reason.
    sfTable = load('Sf_gh10240bw200.mat');
    FitOpt.SfTable = sfTable;
end
