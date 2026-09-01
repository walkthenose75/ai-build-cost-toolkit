# Power Apps Code App integration

These files are generated for the project being measured.

```tsx
import {
  AIC_BASELINE_REPORT,
  AIC_CURRENT_REPORT,
  AiBuildCostPage,
} from './features/ai-build-cost'

<AiBuildCostPage
  title="My Solution - AI Build Cost"
  report={AIC_CURRENT_REPORT}
  baseline={AIC_BASELINE_REPORT}
/>
```

Add the page to the app's existing route/page union and navigation using that
project's conventions. The component has no dependencies beyond React and does
not access Dataverse, connectors, local storage, or the Copilot session store.

Refresh `aic-data.ts` by running `install-code-app-page` again with `--force`
after each approved AIC checkpoint. Keep the baseline report immutable.
