# Public Fixture Demo Summary

Status: fixture proof package, pending visual capture.

This package establishes the safe public data path for the Operator OS /
Portfolio Command Center demo:

- fixture input: `fixtures/demo/sample-report.json`;
- generated artifacts: `output/demo/`, including the PortfolioCommandCenter
  `projects` schema, weekly digest, burndown, trend snapshots, and empty
  proposal queue;
- desktop consumer: `PortfolioCommandCenter` pointed at `output/demo`;
- private services required: none;
- live writes performed: none.

The next step before publishing is to capture screenshots or video frames from
Portfolio Command Center while it is pointed at the fixture output directory,
then add those images to this package.
