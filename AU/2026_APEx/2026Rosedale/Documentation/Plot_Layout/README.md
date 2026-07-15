# Plot Layout — 2026Rosedale

Site-specific notes for the files in this folder. For the
APPN-wide spec see the [Plot Delineation protocol](https://github.com/ArdenB/APPN-Aerial-Standard-Operating-Procedures/blob/main/Protocols/PlotProtocols/PlotDelineation/Plot_Delineation.md).

## Current main file
- `2026Rosedale_plots.geojson` — fitted YYYY-MM-DD by <name>,
  method <FIELDimageR | DPIRD | GPT>.

## Variants in use
- `plots_unbuffered` — used by <pipeline / person> for <reason>.
- `plots_{sensor}` — justified because <CRS / portion-of-plot reason>;
  approved by EWG on <date>.

## Sampling campaigns
- `sampling_biomass_YYYYMMDD…` — operator, quadrat size, anything odd.

## Deprecated files
| File | Replaced on | Reason | Superseded by |
| --- | --- | --- | --- |
| `2026Rosedale_plots_YYYYMMDD_deprecated.geojson` | YYYY-MM-DD | <reason> | `2026Rosedale_plots.geojson` |

## Known issues / quirks
- e.g. "HIRES flight 2025-10-12 had a 7 cm N–S offset — corrected in
  re-process."
