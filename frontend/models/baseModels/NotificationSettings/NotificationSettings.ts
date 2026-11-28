import { FrappeDoc } from 'src/frappe/document';

/**
 * Books Notification Settings, served by Frappe: which push events the shop sends
 * (spec 0026 AC-8). Only Books Manager and System Manager read it.
 */
export class NotificationSettings extends FrappeDoc {
  static override doctype = 'Books Notification Settings';
  static override presentation = {
    label: 'Notifications',
    // Written only by the hourly subscription job.
    omitFields: ['last_subscription_phase'],
  };
}
