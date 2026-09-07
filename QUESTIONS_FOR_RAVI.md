# Questions for Ravi — Meta Analysis Enhancement Proposal

Context: questions on `Meta Analysis_NewV1.docx` (the 4-phase Meta Analysis automation proposal), to clarify scope, priority, and feasibility before estimating any build work.

## On priority and scope

1. Of the 4 phases, which one(s) do you want me to actually scope and estimate for build right now, versus which are long-term direction you want documented but not committed to a timeline?

2. For whichever phase(s) are "now" — is there a target rollout date or milestone (e.g. a specific upcoming Meta Analysis project) this needs to be ready for?

3. Is there a specific second client or engagement already lined up that needs the generalized version, or is "usable for any client" the goal without a concrete second use case yet? I ask because the original tool was deliberately built narrow for one client's file format — I want to build the right amount of flexibility, not more than needed.

4. Once Phase 1 is delivered, should I treat that as a complete, standalone deliverable — not an automatic commitment to start Phase 2 — so we scope 2-4 as separate conversations later?

## On Phase 1 (consolidation automation)

5. The spec calls for validating each new file's structure strictly against the Master file. The original tool instead tolerated column-name variation across sources using an alias map (I hit real differences in column naming across files). Do you want strict exact-match validation this time, or should it still tolerate known naming variants?

6. Resuming an existing project is based on the file being named with a `Master_` prefix. Is filename-based detection acceptable, or should I plan for something more durable — e.g. if the file gets renamed, downloaded twice, or two people work off copies of the same study set?

## On Phase 2 (study search & bulk download)

7. What platform/system actually holds the study search data and score files today? Will I have API or export access to query and bulk-download from it, or is this only accessible through a manual UI right now?

## On Phase 3 (metric enrichment & benchmarking)

8. Where do Total Campaign Cost, Total Campaign Impressions, % Household Buying, Average Purchase Cycle, and Average Brand Price currently come from — which reports or systems? Are those queryable somewhere, or are analysts compiling them manually today? I want to know before estimating, since if there's no systematic source for these yet, that's a data-availability problem, not something Python can solve on its own.

## Gaps and inconsistencies in the doc itself

9. The manual Step 2 description says your tool already "standardizes break names/Model_Desc column" for Antra, but the Phase 1 Functional Requirements only mention adding a Study Name column and validating/appending structure — standardizing break/label names across clients isn't listed. Should that be part of Phase 1? If so, since break names vary by client, what's the standardization logic supposed to be — a lookup table I maintain and extend per client, or something else?

10. The original 5-step manual process ends with "Finalize the story and create final PPT" (4-5 days). None of the 4 phases cover that — Phase 4 stops at "export-ready charts, tables, and summaries." Is final PPT/story assembly intentionally staying manual forever, or is there a Phase 5 that just hasn't been written up yet?

11. File formats and volume: will source files always be .xlsx/.csv across every client, or should I plan for other formats? And roughly how many study files, and how large, make up a typical Meta Analysis (10 files? 100? what size each)? This determines whether a straightforward pandas-based approach holds up or something else is needed.

## On Phase 4 (bucketing, histograms, insight generation)

12. "Automatic generation of recommended bucket ranges based on data distribution" — is there a bucketing method analysts already use today (quantiles, fixed-width ranges, something else), or am I defining that methodology from scratch?

13. "Statistical significance indicators where applicable" — what test and threshold should this use (e.g. t-test on lift, confidence interval), or is there an existing standard the analytics team already follows that I should match?

## On Phase 1 mechanics (additional)

14. In bulk folder mode, the first valid file found becomes the Master and sets the reference schema — first by what ordering (alphabetical, file date, something else)? And if that particular file happens to be missing a column that later files have, is it still treated as authoritative, or should I be able to designate which file defines the schema?

15. Once a Master file's reference schema is set, is it locked for the life of that Meta Analysis project, or does a legitimate new column need to be addable later without every other file suddenly failing validation?

16. When a file fails structure validation and lands in the exception report, what's supposed to happen next — does the user fix the source file and re-run it, or do you want an in-tool way to remap/fix columns before retrying?

## On Phase 3 (derived metric definitions)

17. The derived metrics (ROAS, %Lift, Absolute Difference, Average Weekly Impressions, etc.) aren't defined with formulas. Since these can be computed more than one way (e.g. is %Lift `(Exposed-Control)/Control` or something else; is ROAS revenue/cost or a different ratio), can you give me the exact formula for each so the numbers match what analysts already report?

## On Phase 2 (field list)

18. The search filters and output fields both end in "additional project/key attributes as available" — can you give me the definitive field list you need for a usable MVP, rather than "as available," so I'm not guessing at what the platform actually exposes?

## On phase dependencies

19. Phase 3 depends on Phase 1's consolidated output, and Phase 4 depends on Phase 3's enriched output — so 1 → 3 → 4 is a real chain. Phase 2 is only loosely linked (its output just needs to match Phase 1's input format), but its "Future-State Consideration" suggests it could eventually replace Phase 1's consolidation step entirely (download + append + tag in one shot). Is that future-state a real intention? If so, I'd rather keep Phase 1's append/validation logic simple now instead of over-investing in mechanics that Phase 2 might supersede later.
