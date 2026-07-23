## ADDED Requirements

### Requirement: Research page hosts the exploratory chart sections
The dashboard SHALL serve a second page at `/research`, rendered from its
own template with the same design system (tokens, JetBrains Mono, flat
surfaces, theme toggle behaviour) as the main page. The page SHALL host
the block-propagation section (ECDF + recent-blocks table with per-block
drill-down), the services adoption history small multiples, and the
unique-estimate composition breakdown with its 1/N method description.
Sections SHALL fetch their data lazily and render independently, so one
empty dataset does not block the others.

#### Scenario: Page renders with all sections
- **WHEN** a visitor opens `/research` and all three datasets are available
- **THEN** the propagation, services-history, and unique-composition
  sections render with Observable Plot using design-system tokens, in the
  active theme

#### Scenario: Partial data
- **WHEN** one dataset is empty (e.g., no propagation files yet)
- **THEN** that section shows an empty-state note and the other sections
  render normally

### Requirement: Header navigation links the two pages
Both the main page and the research page SHALL show a header navigation
with two entries (overview and research), styled from design-system
tokens, with the active page visually distinguished. Compact elements on
the main page (services strip, unique-estimate band) SHALL link to their
expanded sections on `/research`.

#### Scenario: Navigating between pages
- **WHEN** a visitor activates the research entry from the main page
- **THEN** the browser navigates to `/research`, where the research entry
  is marked active and an overview entry links back to `/`

#### Scenario: Deep links from compact elements
- **WHEN** the visitor activates the services strip or the unique band's
  link on the main page
- **THEN** they land on the corresponding section of `/research`
