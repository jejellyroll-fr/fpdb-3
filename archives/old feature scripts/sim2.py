# streight forward montecarlo implementaion
def monteCarloMdd_0(S0, mu, sigma, seed, N, N_PATH):
    x = []
    for i in range(N_PATH):
        np.random.seed(seed + i)
        S_final = [] # all price points for one path
        W = 0
        for k in range(1,N+1):
            W += np.random.normal(0, 1) #generate random value
            drift = (mu - 0.5 * sigma**2) * k #for k data point
            diffusion = sigma * W  #for k data point

            S = S0*np.exp(drift + diffusion) #calculate one price point

            S_final.append(S)
        
        x.append(MaxDrawdown(np.array(S_final)))
    return np.mean(x)