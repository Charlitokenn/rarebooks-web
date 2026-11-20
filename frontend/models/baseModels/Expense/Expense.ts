import { Fyo } from 'fyo';
import { Action, FiltersMap, ListViewSettings } from 'fyo/model/types';
import { getDocStatusListColumn, getLedgerLinkAction } from 'models/helpers';
import { FrappeDoc } from 'src/frappe/document';
import { ExpenseAccount } from '../ExpenseAccount/ExpenseAccount';

/**
 * Books Expense, served by Frappe: money already paid out from one account.
 * Its controller fills the number series and the total, checks the accounts
 * and posts the rows to the ledger on submit.
 */
export class Expense extends FrappeDoc {
  static override doctype = 'Books Expense';
  static override presentation = {
    label: 'Expense',
    nameField: { label: 'Expense No' },
    fields: { paid_from: { create: false } },
  };
  static override previewMethod = 'preview';
  static override rowModels = { accounts: ExpenseAccount };
  static override startRows = ['accounts'];

  get isTransactional() {
    return true;
  }

  static filters: FiltersMap = {
    number_series: () => [['reference_type', '=', 'Expense']],
    party: () => [['role', 'in', ['Supplier', 'Both']]],
  };

  static override createFilters: FiltersMap = {
    party: () => [['role', '=', 'Supplier']],
  };

  /** The server runs the rule the save checks, which these filters can't express. */
  static override linkQueries = {
    paid_from:
      'frappe_books.accounting.accounts.search_expense_payment_accounts',
  };

  static getActions(fyo: Fyo): Action[] {
    return [getLedgerLinkAction(fyo)];
  }

  static getListViewSettings(): ListViewSettings {
    return {
      columns: [
        'name',
        getDocStatusListColumn(),
        'date',
        'party',
        'paid_from',
        'total',
      ],
    };
  }
}
