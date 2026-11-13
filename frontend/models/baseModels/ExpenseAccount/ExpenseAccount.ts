import { FrappeDoc } from 'src/frappe/document';

/** A Books Expense Account row: one Expense account and the amount spent on it. */
export class ExpenseAccount extends FrappeDoc {
  static override presentation = {
    label: 'Expense Account',
    fields: { account: { create: false } },
  };

  /**
   * The server offers the leaf Expense accounts the save accepts, gated on
   * the expense rights, so a Books User picks one without account rights.
   * It ignores client filters, so the model sends none.
   */
  static override linkQueries = {
    account: 'frappe_books.accounting.accounts.search_expense_accounts',
  };
}
