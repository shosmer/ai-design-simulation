# We're arguing about the wrong variable

Every debate about AI and design careers turns into a capability debate — how good the models are, how fast they're improving, whether they can really do the work. I spent the last few weeks building a simulation to pressure-test that frame, and the result surprised me: across every capability scenario I ran, the speed of AI progress barely moved the outcome for designers. One variable decided nearly everything, and it's one we almost never argue about.

## The experiment

I wanted to test whether AI's impact on design careers could be modeled instead of argued. So I built an agent-based simulation of the tech design labor market: a few thousand simulated designers across junior, mid, and senior levels, 150 firms deciding month by month which work goes to humans, humans-with-AI, or AI alone, and a talent pipeline that responds to whether juniors are actually getting hired. (Built with agentic coding tools — that was a hypothesis I was testing too.)

The model runs on public data that refreshes on a schedule: BLS employment counts for design occupations, the Census Bureau's biweekly survey of firm AI adoption, Indeed's job postings indices, and the Anthropic Economic Index, which maps real AI usage onto official O*NET task statements. That last source matters. Instead of guessing which design tasks AI does most, I joined the 119 official task statements for design occupations against measured usage. The result is lopsided — design-to-code work shows roughly six times the AI maturity of visual production work, and strategy work barely registers. The "AI does the intern work first" story is real, but in the data I can see, the intern work is prototyping and code, not Photoshop. (One honest caveat: this data observes one AI assistant, so image-tool automation is undercounted.)

Every run gets compared against a paired no-AI counterfactual — the same simulated world, the same random shocks, AI switched off. Everything below is "versus a world where AI never happened," which strips out the post-2022 market correction that gets blamed on AI more than it should.

## What actually decides the outcome

I ran slow, base, and fast capability scenarios, crossed with a range of demand elasticities, with multiple random seeds on each. Capability timing moved the 2035 outcomes by a few percentage points. Demand elasticity moved them by a factor of two or three.

Demand elasticity, in plain terms: when design output gets cheaper, does the world consume more of it?

If the answer is "not much," the model is grim — junior employment lands around 0.6x what it would have been without AI, total design employment shrinks, and the senior-to-junior wage premium climbs from about 2x today to over 3x. Fewer designers, and the ones who remain are senior and expensive.

If the answer is "much more," the same AI produces the opposite world — junior employment at 1.2x the no-AI baseline, total employment up 60 to 80 percent, and the seniority premium compressing as demand pulls people up the ladder.

Same capability curves. Same adoption rates. Opposite outcomes. The fork in the road isn't how good AI gets — it's whether cheaper design expands what gets designed.

## The most useful thing the model did was catch me being wrong

My first version produced a dramatic finding: junior employment collapsed under every assumption. It would have made a great headline, and it was an artifact. When I built the no-AI counterfactual, it showed juniors collapsing with AI switched off — my baseline career ladder wasn't stable, and the "collapse" was leaking out of the model's plumbing, not out of AI.

Fixing it meant making the model more honest: promotions gated by open roles instead of tenure clocks (you move up when a slot opens, not when a timer fires), wages that respond to unfilled roles and unemployment, firms that grow and shrink independently. The corrected model is where the elasticity finding emerged. The lesson travels beyond simulations — a claim you can't difference against a counterfactual is a claim you shouldn't publish.

## What the data can't say yet

I fit the model against 2023–2026 reality: design-adjacent job postings relative to the overall market, calibrated to Census adoption curves. The honest result is that three years of data cannot yet pin down which elasticity world we're in — the fit is too flat to bet on a point estimate. That's exactly why the findings above are ranges, not predictions. Anyone selling you a confident point forecast about design jobs in 2035 is selling.

## What I'd watch instead

If the fate of design careers rides on demand elasticity, the signals worth watching aren't model release notes. Watch whether organizations ship more designed surfaces as design gets cheaper — more products, more experiments, more polish in places that never got design attention before. That's elasticity showing up in the wild.

And for design leaders, one reframe: elasticity isn't weather. Part of the job, now, is making demand for design elastic — finding the products, surfaces, and experiments that absorb cheap design capacity instead of letting the savings convert to headcount cuts. The teams that treat AI as a reason to design more, not a reason to design with fewer people, are choosing which world they end up in.

The data pipelines behind this refresh automatically, so I'll re-run the model as the picture sharpens — the Census adoption numbers and the Anthropic Economic Index both update on a cadence. More soon.
