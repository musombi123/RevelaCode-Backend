import React from 'react';
import DashboardCard from './common/DashboardCard';
import { Settings, Link2, Info } from 'lucide-react';

const dashboardActions = [
  {
    title: 'Settings',
    icon: Settings,
    key: 'onOpenSettings',
    color: 'bg-green-600 dark:bg-green-500'
  },
  {
    title: 'Accounts',
    icon: Link2,
    key: 'onOpenAccounts',
    color: 'bg-pink-600 dark:bg-pink-500'
  },
  {
    title: 'Referential',
    icon: Info,
    key: 'onOpenReferential',
    color: 'bg-yellow-600 dark:bg-yellow-500'
  }
];

export default function UserAccountDashboard(props) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4 mt-2">
      {dashboardActions.map(({ title, icon: Icon, key, color }) => (
        <DashboardCard
          key={title}
          title={title}
          Icon={Icon}
          color={color}
          onClick={props[key]}
        />
      ))}
    </div>
  );
}
