## MODIFIED Requirements

### Requirement: Research page hosts the exploratory chart sections
The dashboard SHALL serve a second page at `/research`, rendered from its
own template with the same design system (tokens, JetBrains Mono, flat
surfaces, theme toggle behaviour) as the main page. The page SHALL host
the block-propagation section (ECDF + recent-blocks table with per-block
drill-down) and the services adoption history small multiples. The
unique-estimate composition section SHALL be removed, with no replacement:
the page is a token-gated workbench for the maintainer's own experiments,
not a surface that owes visitors an explanation. Each section SHALL fetch
its data lazily and render independently, so a section without data shows
an empty state while the others render.

#### Scenario: Sections render independently
- **WHEN** the research page loads and one section's data is unavailable
- **THEN** that section shows an empty-state note and the other sections
  render normally

#### Scenario: Composition section is gone
- **WHEN** the research page loads
- **THEN** no N-composition bar and no 1/N method description are rendered
