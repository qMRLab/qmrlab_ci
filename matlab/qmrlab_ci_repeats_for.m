function n = qmrlab_ci_repeats_for(repeats, modelId)
    if isfield(repeats, modelId)
        n = double(repeats.(modelId));
    elseif isfield(repeats, 'default')
        n = double(repeats.default);
    else
        n = 1;
    end
end
