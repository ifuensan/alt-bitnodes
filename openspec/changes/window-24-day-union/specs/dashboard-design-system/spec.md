## ADDED Requirements

### Requirement: The header fits every control without horizontal overflow

The page header SHALL lay out identity and navigation (title, tabs, theme
toggle) on a first row and, on the Overview, the view controls (view toggle,
snapshot picker, meta line) on a second toolbar row. The rows SHALL wrap
rather than overflow: at any viewport width from 360 px up, no header
control SHALL be clipped and the page SHALL NOT scroll horizontally because
of the header. The Archive and Research pages SHALL use the same first-row
layout.

#### Scenario: Desktop width
- **WHEN** the Overview is viewed at 1400 px in the 24-day union view
- **THEN** the title, tabs and theme toggle share the first row, and the
  three view buttons and the meta line fit on the toolbar row

#### Scenario: Phone width
- **WHEN** the Overview is viewed at 400 px
- **THEN** the controls wrap onto additional lines and the document width
  equals the viewport width
