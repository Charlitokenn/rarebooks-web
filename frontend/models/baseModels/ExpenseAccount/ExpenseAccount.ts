import { FiltersMap } from 'fyo/model/types';
import { FrappeDoc } from 'src/frappe/document';

/** A Books Expense Account row: one Expense account and the amount spent on it. */
export class ExpenseAccount extends FrappeDoc {
  static override presentation = {
    label: 'Expense Account',
    fields: { account: { create: false } },
  };

  /** Mirrors the controller, which takes only leaf Expense accounts. */
  static filters: FiltersMap = {
    account: () => [
      ['is_group', '=', 0],
      ['root_type', '=', 'Expense'],
    ],
  };
}
