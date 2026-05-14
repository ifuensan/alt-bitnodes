## MODIFIED Requirements

### Requirement: Dark theme styling
Bar charts SHALL be styled from the dashboard's design-system tokens and SHALL follow the active theme (dark or light), rather than hard-coded hex values.

#### Scenario: Visual styling
- **WHEN** a chart is rendered
- **THEN** bar fill comes from the `primary` token, the figure background is transparent, axis text uses the active theme's text token, and X-axis grid lines use a border token — all resolved from the current theme, not literal hex values

#### Scenario: Dynamic height
- **WHEN** a chart is rendered with `n` bars
- **THEN** its height scales with `n` (a fixed per-bar height plus top/bottom margins) so every bar has enough vertical room for its label, instead of a fixed 240px height

#### Scenario: Follows theme switch
- **WHEN** the user toggles between dark and light themes
- **THEN** the chart re-renders with the new theme's token values
