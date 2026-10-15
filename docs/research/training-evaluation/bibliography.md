# Bibliography and Source to Claim Map

## Original publications supporting the training evaluation chapter

**Checked 15 October 2026.** This bibliography accompanies [Evaluating and Visually Understanding Model Training Runs](evaluating-and-visually-understanding-training-runs.md). It identifies the original publication, the claim used in the chapter, and the boundary of that evidence. Proceedings pages, publisher records, author-hosted papers, or author-deposited preprints were used. A repository report is listed separately as project evidence.

“Peer-reviewed” below identifies the publication venue, not a guarantee that every conclusion generalizes. An arXiv link is an accessible author version and does not itself establish peer review. The literature search is a targeted research synthesis, not a systematic review with an exhaustive inclusion protocol. No universal method ranking or state-of-the-art claim is made as of the checked date.

## Optimization and learning mechanisms

### R1 Backpropagation

Rumelhart, D. E., Hinton, G. E., & Williams, R. J. (1986). Learning representations by back-propagating errors. *Nature, 323*, 533–536. [Original publisher record](https://doi.org/10.1038/323533a0).

**Status:** peer-reviewed journal article. **Used in:** Section 1.1, explaining gradients through neural computations. **Limit:** cited as a classic formulation, not a claim that this article is the sole historical origin of automatic differentiation or backpropagation, nor a guarantee that any chosen objective is correct.

### R2 Stochastic reward gradients

Williams, R. J. (1992). Simple statistical gradient-following algorithms for connectionist reinforcement learning. *Machine Learning, 8*, 229–256. [Original publisher record](https://link.springer.com/article/10.1007/BF00992696).

**Status:** peer-reviewed journal article. **Used in:** Section 2.4, the distinction between differentiating a policy probability and differentiating an external reward. **Limit:** stochastic-unit and policy-gradient reasoning does not give an arbitrary deterministic field predictor a direct gradient from a human rating.

### R12 Early stopping

Prechelt, L. (1998). Early stopping—But when? In G. B. Orr & K.-R. Müller (Eds.), *Neural Networks: Tricks of the Trade*, Lecture Notes in Computer Science 1524, pp. 55–69. Springer. [Author-hosted manuscript](https://page.mi.fu-berlin.de/prechelt/Biblio/stop_tricks1997.pdf); [publication record](https://publikationen.bibliothek.kit.edu/7498).

**Status:** published research chapter; linked manuscript predates the book publication. **Used in:** Section 7.3, selecting stopping rules from validation behavior. **Limit:** a practical empirical study, not a universal optimal stopping rule for every modern learner.

### R13 Nonmonotone generalization curves

Nakkiran, P., Kaplun, G., Bansal, Y., Yang, T., Barak, B., & Sutskever, I. (2020). Deep double descent: Where bigger models and more data hurt. *International Conference on Learning Representations*. [Author preprint submitted in 2019](https://arxiv.org/abs/1912.02292); [official ICLR 2020 program](https://iclr.cc/virtual_2020/papers.html).

**Status:** peer-reviewed conference paper; arXiv version is the author preprint. **Used in:** Section 7.3, cautioning against a universal U-shaped validation story. **Limit:** reports particular settings and proposed explanations, not that continued fitting will rescue every worsening run.

### R14 Activation and gradient propagation

Glorot, X., & Bengio, Y. (2010). Understanding the difficulty of training deep feedforward neural networks. *AISTATS*, PMLR 9, 249–256. [Original proceedings](https://proceedings.mlr.press/v9/glorot10a.html).

**Status:** peer-reviewed conference paper. **Used in:** Section 8.2, activation saturation, layerwise propagation, and initialization diagnostics. **Limit:** its studied architectures do not make one activation histogram a definitive diagnosis for every network.

### R15 Recurrent gradient pathologies

Pascanu, R., Mikolov, T., & Bengio, Y. (2013). On the difficulty of training recurrent neural networks. *ICML*, PMLR 28(3), 1310–1318. [Original proceedings](https://proceedings.mlr.press/v28/pascanu13.html).

**Status:** peer-reviewed conference paper. **Used in:** Section 8.2, vanishing/exploding gradients and norm clipping. **Limit:** clipping can manage large updates without identifying or removing every source of instability.

### R16 Composite physics objectives

Wang, S., Teng, Y., & Perdikaris, P. (2021). Understanding and mitigating gradient flow pathologies in physics-informed neural networks. *SIAM Journal on Scientific Computing, 43*(5), A3055–A3081. [Original publisher record](https://doi.org/10.1137/20M1318043); [author preprint](https://arxiv.org/abs/2001.04536).

**Status:** peer-reviewed journal article; preprint title differs slightly. **Used in:** Section 8.3, component loss and gradient imbalance. **Limit:** the studied PINN mechanisms are not an automatic diagnosis of a supervised CNN or a universal prescription for loss weights.

## Data evaluation and experimental validity

### R3 Verification and physical validation

Oberkampf, W. L., & Trucano, T. G. (2002). Verification and validation in computational fluid dynamics. *Progress in Aerospace Sciences, 38*(3), 209–272. [Original publisher DOI](https://doi.org/10.1016/S0376-0421(02)00005-2).

**Status:** peer-reviewed review and methodological journal article. **Used in:** Section 3.4, distinguishing numerical verification, physical validation, and prediction. **Limit:** numerical agreement or a low residual alone is not observational validation of the mathematical model.

### R4 Selection bias

Cawley, G. C., & Talbot, N. L. C. (2010). On over-fitting in model selection and subsequent selection bias in performance evaluation. *Journal of Machine Learning Research, 11*, 2079–2107. [Original journal page](https://www.jmlr.org/papers/v11/cawley10a.html).

**Status:** peer-reviewed journal article. **Used in:** Sections 4.1 and 15, treating checkpoint and hyperparameter selection as part of the evaluated procedure. **Limit:** avoiding selection bias still requires a suitable sampling and independence design.

### R5 Leakage in scientific machine learning

Kapoor, S., & Narayanan, A. (2023). Leakage and the reproducibility crisis in machine-learning-based science. *Patterns, 4*(9), 100804. [Original publisher DOI](https://doi.org/10.1016/j.patter.2023.100804); [author preprint](https://arxiv.org/abs/2207.07048).

**Status:** peer-reviewed journal article; the earlier preprint has a different version and title capitalization. **Used in:** Section 4.2, auditing leakage throughout the pipeline. **Limit:** no prevalence statistics from differently dated versions are mixed, and no universal split is attributed to the paper.

### R6 Declared distribution shifts

Koh, P. W., Sagawa, S., Marklund, H., et al. (2021). WILDS: A benchmark of in-the-wild distribution shifts. *ICML*, PMLR 139, 5637–5664. [Original proceedings and full author list](https://proceedings.mlr.press/v139/koh21a.html).

**Status:** peer-reviewed conference benchmark paper. **Used in:** Section 4.3, separating ordinary holdout from specified domain shifts. **Limit:** its application-domain findings are methodological motivation, not evidence for a particular physics surrogate.

### R7 Example learning histories

Swayamdipta, S., Schwartz, R., Lourie, N., Wang, Y., Hajishirzi, H., Smith, N. A., & Choi, Y. (2020). Dataset cartography: Mapping and diagnosing datasets with training dynamics. *EMNLP*, 9275–9293. [Original proceedings](https://aclanthology.org/2020.emnlp-main.746/).

**Status:** peer-reviewed conference paper. **Used in:** Section 5.4, model-dependent per-example histories across training. **Limit:** regression adaptations are proposed diagnostic analogies; a high error or varying confidence is not proof of a bad label.

### R39 Reporting development budgets

Dodge, J., Gururangan, S., Card, D., Schwartz, R., & Smith, N. A. (2019). Show your work: Improved reporting of experimental results. *EMNLP-IJCNLP*, 2185–2194. [Original proceedings](https://aclanthology.org/D19-1224/).

**Status:** peer-reviewed conference paper. **Used in:** Section 15.1, declaring search and computational budgets. **Limit:** its NLP comparisons motivate transparent accounting rather than prescribing an identical budget unit for all systems.

### R42 Hidden variation behind similar scores

D'Amour, A., Heller, K., Moldovan, D., et al. (2022). Underspecification presents challenges for credibility in modern machine learning. *Journal of Machine Learning Research, 23*(226), 1–61. [Original journal page and full author list](https://jmlr.org/papers/v23/20-1335.html).

**Status:** peer-reviewed journal article. **Used in:** Section 19, similar standard scores can conceal divergent stress behavior. **Limit:** does not establish which hidden behavior a new model has; targeted evidence remains necessary.

### R43 Statistical uncertainty across limited runs

Agarwal, R., Schwarzer, M., Castro, P. S., Courville, A., & Bellemare, M. G. (2021). Deep reinforcement learning at the edge of the statistical precipice. *Advances in Neural Information Processing Systems, 34*. [Original proceedings](https://proceedings.neurips.cc/paper/2021/hash/f514cec81cb148559cf475e7426eed5e-Abstract.html).

**Status:** peer-reviewed conference paper. **Used in:** Section 15.5, interval estimates, variability, and caution with limited runs. **Limit:** task/run resampling in RL must be adapted to the dependence structure of another domain; resampling does not cure leakage.

## Metrics and visual interpretation

### R8 Structural image similarity

Wang, Z., Bovik, A. C., Sheikh, H. R., & Simoncelli, E. P. (2004). Image quality assessment: From error visibility to structural similarity. *IEEE Transactions on Image Processing, 13*(4), 600–612. [Author/institution-hosted original paper](https://www.colorado.edu/lab/live/publications/zwang_ssim_ieeeip2004.pdf).

**Status:** peer-reviewed journal article. **Used in:** Section 6.1, explaining SSIM's intended structural similarity role. **Limit:** no claim that SSIM measures physical validity, factuality, or every aspect of perception.

### R9 Deep perceptual image similarity

Zhang, R., Isola, P., Efros, A. A., Shechtman, E., & Wang, O. (2018). The unreasonable effectiveness of deep features as a perceptual metric. *CVPR*, 586–595. [Original accepted conference paper](https://openaccess.thecvf.com/content_cvpr_2018/html/Zhang_The_Unreasonable_Effectiveness_CVPR_2018_paper.html).

**Status:** peer-reviewed conference paper. **Used in:** Section 6.1, LPIPS and perceptual evaluation. **Limit:** natural-image perceptual evidence is not a test of numerical field values or governing equations.

### R10 Reference based translation evaluation

Papineni, K., Roukos, S., Ward, T., & Zhu, W.-J. (2002). Bleu: A method for automatic evaluation of machine translation. *ACL*, 311–318. [Original proceedings](https://aclanthology.org/P02-1040/).

**Status:** peer-reviewed conference paper. **Used in:** Section 6.1, metrics have a particular task and reference policy. **Limit:** reference overlap is not a general factual-correctness or task-success guarantee.

### R17 Quantitative graphical perception

Cleveland, W. S., & McGill, R. (1984). Graphical perception: Theory, experimentation, and application to the development of graphical methods. *Journal of the American Statistical Association, 79*(387), 531–554. [Institution-hosted original paper](https://faculty.washington.edu/aragon/classes/hcde511/s12/readings/cleveland84.pdf).

**Status:** peer-reviewed journal article with perceptual experiments. **Used in:** Section 9.1, selecting quantitatively readable encodings. **Limit:** the studied elementary tasks do not establish one optimal visualization for every scientific question or audience.

### R18 Color map artifacts

Borland, D., & Taylor, R. M., II. (2007). Rainbow color map (still) considered harmful. *IEEE Computer Graphics and Applications, 27*(2), 14–17. [Original publisher DOI](https://doi.org/10.1109/MCG.2007.323435); [bibliographic record](https://pubmed.ncbi.nlm.nih.gov/17388198/).

**Status:** published journal methodological article. **Used in:** Section 9.1, color maps can create misleading perceptual emphasis. **Limit:** a better color map still needs correct scales, units, and a suitable task representation. DOI access can vary; the bibliographic record verifies publication details.

### R19 Checking visual explanations

Adebayo, J., Gilmer, J., Muelly, M., Goodfellow, I., Hardt, M., & Kim, B. (2018). Sanity checks for saliency maps. *Advances in Neural Information Processing Systems, 31*. [Original proceedings](https://papers.nips.cc/paper/2018/hash/294a8ed24b1ad22ec2e7efea049b8737-Abstract.html).

**Status:** peer-reviewed conference paper. **Used in:** Section 9.3, randomization checks and limits of visual appeal. **Limit:** passing a diagnostic check is not a certificate of causal explanation or universal faithfulness.

### R20 Loss landscape visualization

Li, H., Xu, Z., Taylor, G., Studer, C., & Goldstein, T. (2018). Visualizing the loss landscape of neural nets. *Advances in Neural Information Processing Systems, 31*. [Original proceedings](https://proceedings.neurips.cc/paper/2018/hash/a41b3bb3e6b050b6c9067c67f663b915-Abstract.html).

**Status:** peer-reviewed conference paper. **Used in:** Section 9.3, filter-normalized projected loss plots. **Limit:** these plots remain selected low-dimensional views of a high-dimensional objective.

### R21 Parameterization and sharpness

Dinh, L., Pascanu, R., Bengio, S., & Bengio, Y. (2017). Sharp minima can generalize for deep nets. *ICML*, PMLR 70, 1019–1028. [Original proceedings](https://proceedings.mlr.press/v70/dinh17b.html).

**Status:** peer-reviewed conference paper. **Used in:** Section 9.3, parameter transformations can alter apparent sharpness without changing predictions. **Limit:** the chapter does not conclude that every carefully defined sharpness measure is useless.

## Physical models numerical solvers and benchmarks

### R11 Diverse physical fields and metric normalization

Ohana, R., McCabe, M., Meyer, L., et al. (2024). The Well: A large-scale collection of diverse physics simulations for machine learning. *NeurIPS Datasets and Benchmarks Track*, Advances in Neural Information Processing Systems 37. [Original proceedings and full author list](https://proceedings.neurips.cc/paper_files/paper/2024/hash/4f9a5acd91ac76569f2fe291b1f4772b-Abstract-Datasets_and_Benchmarks_Track.html); [full paper](https://proceedings.neurips.cc/paper_files/paper/2024/file/4f9a5acd91ac76569f2fe291b1f4772b-Paper-Datasets_and_Benchmarks_Track.pdf).

**Status:** peer-reviewed conference benchmark paper. **Used in:** Section 6.2, variance-scaled errors and field/rollout breakdowns; appendix E.3 supplies definitions. **Limit:** target spatial mean is an oracle diagnostic comparator; benchmark baselines are not universal model rankings.

### R22 Learned particle simulation

Sanchez-Gonzalez, A., Godwin, J., Pfaff, T., Ying, R., Leskovec, J., & Battaglia, P. W. (2020). Learning to simulate complex physics with graph networks. *ICML*, PMLR 119, 8459–8468. [Original proceedings](https://proceedings.mlr.press/v119/sanchez-gonzalez20a.html).

**Status:** peer-reviewed conference paper. **Used in:** Sections 10.1 and 12.3, graph representations and distinct rollout behavior. **Limit:** particle representations, noise training, and tested regimes do not directly transfer to every Eulerian pressure problem.

### R23 Learned mesh simulation

Pfaff, T., Fortunato, M., Sanchez-Gonzalez, A., & Battaglia, P. W. (2021). Learning mesh-based simulation with graph networks. *International Conference on Learning Representations*. [Author version with publication reference](https://arxiv.org/abs/2010.03409); [author publication page](https://tobiaspfaff.com/publication/pfaff-2021-learning/).

**Status:** peer-reviewed conference paper; linked arXiv document is an author version. **Used in:** Sections 10.1 and 12.3, mesh-based predictors and rollout evaluation. **Limit:** reported scaling and efficiency are setup-specific, not an unrestricted mesh- or resolution-transfer guarantee.

### R24 Neural operators

Li, Z., Kovachki, N., Azizzadenesheli, K., Liu, B., Bhattacharya, K., Stuart, A., & Anandkumar, A. (2021). Fourier neural operator for parametric partial differential equations. *International Conference on Learning Representations*. [Author preprint](https://arxiv.org/abs/2010.08895); [original accepted-paper PDF](https://openreview.net/pdf/53c47f849d1cd4d21b865caf7d774e07a5c42aa4.pdf).

**Status:** peer-reviewed conference paper; preprint originally submitted in 2020. **Used in:** Section 10.1, operator learning as a distinct representation. **Limit:** the chapter does not generalize reported speedups or super-resolution results to arbitrary geometries, equations, or pressure tasks.

### R25 A learned component inside CFD

Kochkov, D., Smith, J. A., Alieva, A., Wang, Q., Brenner, M. P., & Hoyer, S. (2021). Machine learning–accelerated computational fluid dynamics. *Proceedings of the National Academy of Sciences, 118*(21), e2101784118. [Original publisher DOI](https://doi.org/10.1073/pnas.2101784118); [author preprint](https://arxiv.org/abs/2102.01010).

**Status:** peer-reviewed journal article. **Used in:** Section 10.1, hybrid learned numerical components. **Limit:** the study is principally two-dimensional turbulent CFD; it does not establish acceleration for an unrelated 3D model.

### R26 Pressure projection

Chorin, A. J. (1968). Numerical solution of the Navier-Stokes equations. *Mathematics of Computation, 22*(104), 745–762. [Original publisher DOI](https://doi.org/10.1090/S0025-5718-1968-0242392-2); [author-hosted paper](https://math.berkeley.edu/~chorin/chorin68.pdf).

**Status:** peer-reviewed journal article. **Used in:** Section 11.1, classical pressure/velocity projection context. **Limit:** the chapter's simplified discrete identity is its own stated algebraic derivation, not a universal implementation formula or a learned-solver convergence claim.

### R27 Iterative residual minimization

Saad, Y., & Schultz, M. H. (1986). GMRES: A generalized minimal residual algorithm for solving nonsymmetric linear systems. *SIAM Journal on Scientific and Statistical Computing, 7*(3), 856–869. [Original publisher DOI](https://doi.org/10.1137/0907058).

**Status:** peer-reviewed journal article. **Used in:** Section 11.4, why operator and iterative method matter to an initial guess. **Limit:** no assertion that the motivating project uses GMRES or that lower initial residual always means lower solve time.

### R28 Physics aware benchmark metrics

Takamoto, M., Praditia, T., Leiteritz, R., MacKinlay, D., Alesiani, F., Pflüger, D., & Niepert, M. (2022). PDEBench: An extensive benchmark for scientific machine learning. *NeurIPS Datasets and Benchmarks Track*, Advances in Neural Information Processing Systems 35. [Original proceedings](https://proceedings.neurips.cc/paper_files/paper/2022/hash/0a9747136d411fb83f0cf81820d44afb-Abstract-Datasets_and_Benchmarks.html); [full paper](https://proceedings.neurips.cc/paper_files/paper/2022/file/0a9747136d411fb83f0cf81820d44afb-Paper-Datasets_and_Benchmarks.pdf).

**Status:** peer-reviewed conference benchmark paper. **Used in:** Section 12.1, boundary, conservation, maximum, and frequency-based evaluation beyond global averages. **Limit:** benchmark metric categories require equation- and discretization-specific interpretation.

### R29 Physics informed fitting

Raissi, M., Perdikaris, P., & Karniadakis, G. E. (2019). Physics-informed neural networks: A deep learning framework for solving forward and inverse problems involving nonlinear partial differential equations. *Journal of Computational Physics, 378*, 686–707. [Original publisher DOI](https://doi.org/10.1016/j.jcp.2018.10.045).

**Status:** peer-reviewed journal article. **Used in:** Section 12.2, fitting with equations and conditions. **Limit:** a residual penalty or the label “physics informed” does not provide a universal certificate for an arbitrary surrogate.

### R40 Learned pressure and spatial context

Tompson, J., Schlachter, K., Sprechmann, P., & Perlin, K. (2017). Accelerating Eulerian fluid simulation with convolutional networks. *ICML*, PMLR 70, 3424–3433. [Original proceedings](https://proceedings.mlr.press/v70/tompson17a.html); [full paper](https://proceedings.mlr.press/v70/tompson17a/tompson17a.pdf).

**Status:** peer-reviewed conference paper. **Used in:** Section 15.1, local context and multiscale pressure hypotheses; Sections 4 and 6 provide directly relevant pressure-training and gauge context. **Limit:** findings in that setup motivate a controlled test, not a causal diagnosis of the managed CNN result.

### R41 Accuracy matched hybrid solver timing

Ajuria Illarramendi, E., Bauerheim, M., & Cuenot, B. (2022). Performance and accuracy assessments of an incompressible fluid solver coupled with a deep convolutional neural network. *Data-Centric Engineering, 3*, e2. [Original journal article](https://doi.org/10.1017/dce.2022.2).

**Status:** peer-reviewed journal article. **Used in:** Section 15.2, inference, pressure-projection, and full-fluid-iteration timing at controlled accuracy. **Limit:** empirical comparisons of divergence criteria and particular hybrid methods do not establish universal stability or error bounds.

## Predictive uncertainty and calibration

### R30 Ensembles

Lakshminarayanan, B., Pritzel, A., & Blundell, C. (2017). Simple and scalable predictive uncertainty estimation using deep ensembles. *Advances in Neural Information Processing Systems, 30*. [Original proceedings](https://proceedings.neurips.cc/paper/2017/hash/9ef2ed4b7fd2c810847ffa5fa85bce38-Abstract.html).

**Status:** peer-reviewed conference paper. **Used in:** Section 13.1, combining independently fitted predictors for uncertainty. **Limit:** ensemble agreement is not a correctness guarantee, and shared blind spots remain possible.

### R31 Classification calibration

Guo, C., Pleiss, G., Sun, Y., & Weinberger, K. Q. (2017). On calibration of modern neural networks. *ICML*, PMLR 70, 1321–1330. [Original proceedings](https://proceedings.mlr.press/v70/guo17a.html).

**Status:** peer-reviewed conference paper. **Used in:** Section 13.2, reliability and temperature scaling for classification. **Limit:** does not prescribe continuous-field calibration, simultaneous coverage, or calibration under arbitrary shift.

### R32 Proper probabilistic scoring

Gneiting, T., & Raftery, A. E. (2007). Strictly proper scoring rules, prediction, and estimation. *Journal of the American Statistical Association, 102*(477), 359–378. [Original publisher DOI](https://doi.org/10.1198/016214506000001437); [author-hosted paper](https://sites.stat.washington.edu/people/raftery/Research/PDF/Gneiting2007jasa.pdf).

**Status:** peer-reviewed journal article. **Used in:** Section 13.2, assessing predictive distributions through proper scores. **Limit:** expected-score properties do not make finite samples conclusive or an incorrectly specified forecast distribution correct.

### R33 Marginal conformal coverage

Romano, Y., Patterson, E., & Candès, E. J. (2019). Conformalized quantile regression. *Advances in Neural Information Processing Systems, 32*. [Original proceedings](https://proceedings.neurips.cc/paper_files/paper/2019/hash/5103c3584b063c431bd1268e9b5e76fb-Abstract.html).

**Status:** peer-reviewed conference paper. **Used in:** Section 13.3, finite-sample marginal interval coverage under exchangeability. **Limit:** does not automatically give conditional, whole-field, or arbitrary-shift coverage.

### R34 Online coverage under shift

Gibbs, I., & Candès, E. (2021). Adaptive conformal inference under distribution shift. *Advances in Neural Information Processing Systems, 34*. [Original proceedings](https://proceedings.neurips.cc/paper/2021/hash/0d441de75945e5acbc865406fc9a2559-Abstract.html).

**Status:** peer-reviewed conference paper. **Used in:** Section 13.3, distinguishing long-run online coverage frequency from one-step assurance. **Limit:** frequency control does not promise informative widths or rule out consequential individual misses.

### R35 Uncertainty under dataset shift

Ovadia, Y., Fertig, E., Ren, J., Nado, Z., Sculley, D., Nowozin, S., Dillon, J., Lakshminarayanan, B., & Snoek, J. (2019). Can you trust your model's uncertainty? Evaluating predictive uncertainty under dataset shift. *Advances in Neural Information Processing Systems, 32*. [Original proceedings](https://proceedings.neurips.cc/paper/2019/hash/8558cb408c1d76621371888657d2eb1d-Abstract.html).

**Status:** peer-reviewed conference benchmark paper. **Used in:** Section 13.4, re-evaluating uncertainty under shifted inputs. **Limit:** classification benchmark method rankings do not directly establish uncertainty quality for physical fields.

## Preferences rewards and proxy optimization

### R36 Learning rewards from human comparisons

Christiano, P. F., Leike, J., Brown, T., Martic, M., Legg, S., & Amodei, D. (2017). Deep reinforcement learning from human preferences. *Advances in Neural Information Processing Systems, 30*. [Original proceedings](https://proceedings.neurips.cc/paper/2017/hash/d5e2c0adad503c91f91df240d0cd4e49-Abstract.html).

**Status:** peer-reviewed conference paper. **Used in:** Section 14.3, comparison-derived rewards and policy learning. **Limit:** success in tested RL environments does not establish that human preference optimization is necessary or sufficient for a labeled pressure surrogate.

### R37 Direct preference optimization

Rafailov, R., Sharma, A., Mitchell, E., Manning, C. D., Ermon, S., & Finn, C. (2023). Direct preference optimization: Your language model is secretly a reward model. *Advances in Neural Information Processing Systems, 36*. [Original proceedings](https://proceedings.neurips.cc/paper_files/paper/2023/hash/a85b405ed65c6477a4fe8302b5e06ce7-Abstract.html).

**Status:** peer-reviewed conference paper. **Used in:** Section 14.3, direct preference training under a policy/reference formulation. **Limit:** its original assumptions and log-probability structure cannot simply be assumed for an arbitrary deterministic continuous-field predictor.

### R38 Proxy reward overoptimization

Gao, L., Schulman, J., & Hilton, J. (2023). Scaling laws for reward model overoptimization. *ICML*, PMLR 202, 10835–10866. [Original proceedings](https://proceedings.mlr.press/v202/gao23h.html).

**Status:** peer-reviewed conference paper. **Used in:** Section 14.4, optimizing a proxy can reduce the intended quality. **Limit:** the gold-standard evaluator is another model in a synthetic experimental setup; it is not direct human or physical truth.

## Project evidence and authored illustrations

### P1 Managed CNN qualification report

*Managed captured-data CNN qualification*. Reported execution date 14 October 2026. Repository file pinned to Tuldok commit `f7543fb78f6f1cb52e45dd315efa17a4b2fe6fa6`. [Pinned report](https://github.com/MrScripty/Tuldok/blob/f7543fb78f6f1cb52e45dd315efa17a4b2fe6fa6/docs/plans/generic-neural-execution/reports/managed-cnn.md).

**Status:** project execution report, not peer-reviewed research. **Used in:** Section 10.2, illustrating successful managed fitting/restoration alongside failed numerical qualification. **Reported facts used:** 200 Adam updates, eight fitting cases, normalized fitting MSE approximately 1.600599 to 0.0584414, and zero of 16 restored cases qualified under the pressure/divergence criterion. **Limit:** the report and its declared exposure were read; underlying payloads were not independently rerun or fully audited for this chapter. Its previously exposed test family is not treated as fresh independent evidence. It is not conflated with an older warm-start experiment.

### A Authored examples

The four-clock diagram, checkpoint score table, learning/rollout curves, autoscaling illustration, reversed-velocity calculation, two-value variance example, forced uniform-flow solution, constant pressure offset, alternating-pressure stencil, paired family differences, and fallback timing arithmetic were constructed for this chapter. They are not measured training outcomes. The calculus and arithmetic are conditional on their displayed assumptions; their numbers do not prescribe universal acceptance thresholds.

## Short reading route

For foundational competence, read R1, R4, R14, and R17 after the chapter's opening sections. For pressure surrogates, read R26, R40, and R41 alongside Sections 10–12, then use R28 and R11 to think about broader metrics. For uncertainty, read R31 and R32 before R33–R35. For human quality scoring, start with the score-versus-update distinction in Section 14 and then read R2, R36, and R38; R37 is a specific language-policy method, not the universal next step.
