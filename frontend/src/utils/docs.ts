import { ModelNameEnum } from 'models/types';
import { watch } from 'vue';
import { docsPathRef } from './refs';

/**
 * The RareBooks docs, served at the root of the marketing site. The only place the docs address
 * lives; every docs link is built from it by `docsUrl` (spec 0015 AC-2).
 */
export const DOCS_BASE_URL = 'https://rarebooks.cc';

/** Opened when a screen has no docs page and no overview to fall back to (spec 0015 AC-4). */
export const DOCS_HOME = '/getting-started/getting-started-with-rarebooks/';

/**
 * Each screen's page on the RareBooks docs, in Starlight's canonical form (leading and trailing
 * slash, so no redirect). Every value must be a key of `tests/docs_pages.json` (spec 0015 AC-8).
 * Screens with no page of their own point at the nearest one until they get it (AC-4); the GST
 * reports have no entry, so they take the Reports fallback.
 */
export const docsPathMap: Record<string, string | undefined> = {
  // Analytics
  Dashboard: '/basics/dashboard/',
  Reports: '/financial-reports/reports/',
  GeneralLedger: '/financial-reports/general-ledger/',
  ProfitAndLoss: '/financial-reports/profit-and-loss-statement/',
  BalanceSheet: '/financial-reports/balance-sheet/',
  TrialBalance: '/financial-reports/trial-balance/',

  // Transactions
  [ModelNameEnum.SalesQuote]: '/transactions/sales-invoice/',
  [ModelNameEnum.SalesInvoice]: '/transactions/sales-invoice/',
  [ModelNameEnum.PurchaseInvoice]: '/transactions/purchase-invoice/',
  [ModelNameEnum.Payment]: '/transactions/payments/',
  [ModelNameEnum.Expense]: '/transactions/payments/',
  [ModelNameEnum.JournalEntry]: '/transactions/journal-entries/',
  [ModelNameEnum.LoyaltyProgram]: '/transactions/loyalty-program/',
  [ModelNameEnum.Lead]: '/transactions/lead/',
  POS: '/transactions/point-of-sale/',
  [ModelNameEnum.POSSettings]: '/transactions/point-of-sale/',
  [ModelNameEnum.PricingRule]: '/masters/pricing-rule/',
  [ModelNameEnum.CouponCode]: '/masters/coupon-code/',

  // Inventory
  [ModelNameEnum.StockMovement]: '/inventory/stock-movement/',
  [ModelNameEnum.Shipment]: '/inventory/shipment/',
  [ModelNameEnum.PurchaseReceipt]: '/inventory/purchase-receipt/',
  StockLedger: '/inventory/stock-ledger/',
  StockBalance: '/inventory/stock-balance/',
  [ModelNameEnum.Batch]: '/inventory/batches/',
  [ModelNameEnum.SerialNumber]: '/inventory/serial-number/',
  [ModelNameEnum.InventorySettings]: '/inventory/inventory-settings/',

  // Entries
  Entries: '/masters/master-data/',
  [ModelNameEnum.Party]: '/masters/party/',
  [ModelNameEnum.Item]: '/masters/items/',
  [ModelNameEnum.Tax]: '/masters/taxes/',
  [ModelNameEnum.PriceList]: '/masters/price-list/',
  [ModelNameEnum.PrintFormat]: '/settings/print-templates/',

  // Miscellaneous
  Search: '/getting-started/quick-search/',
  NumberSeries: '/settings/number-series/',
  ImportWizard: '/getting-started/import-wizard/',
  Settings: '/settings/settings/',
  ChartOfAccounts: '/getting-started/chart-of-accounts/',
  [ModelNameEnum.CustomForm]: '/settings/customize-form/',
};

/** A docs link: an empty path opens the docs home, never the bare site (spec 0015 AC-2, AC-4). */
export function docsUrl(path: string, anchor?: string): string {
  return DOCS_BASE_URL + (path || DOCS_HOME) + (anchor ? '#' + anchor : '');
}

/** Opens docs in a new tab that can't reach the app window (spec 0015 AC-3). */
export function openDocs(path: string, anchor?: string): void {
  window.open(docsUrl(path, anchor), '_blank', 'noopener,noreferrer');
}

/** The active Settings tab's page when it has one, else the Settings page (spec 0015 AC-7). */
export function settingsDocsPath(tab: string): string {
  return docsPathMap[tab] ?? docsPathMap.Settings ?? DOCS_HOME;
}

/**
 * Points Documentation at `path` for an overlay, such as the Settings dialog, while it is open.
 * A screen that sets its own path meanwhile does not take over: on a cold load the dialog opens
 * before the Dashboard under it activates. Its path is kept as the one `release()` puts back,
 * so closing returns to whichever screen is underneath by then (spec 0015 AC-7).
 */
export function holdDocsPath(path: string): {
  update(path: string): void;
  release(): void;
} {
  let underneath = docsPathRef.value;
  let held = path;
  docsPathRef.value = held;
  const stop = watch(
    docsPathRef,
    (value) => {
      if (value !== held) {
        underneath = value;
        docsPathRef.value = held;
      }
    },
    { flush: 'sync' }
  );
  return {
    update(next: string) {
      held = next;
      docsPathRef.value = next;
    },
    release() {
      stop();
      docsPathRef.value = underneath;
    },
  };
}
