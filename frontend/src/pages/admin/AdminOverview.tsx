import { useEffect, useState } from 'react';
import AdminLayout from '@/components/admin/AdminLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Users, PenTool, Mic, Bot } from 'lucide-react';
import { fetchJson } from '@/lib/backend';

type OverviewStats = {
  total_users: number;
  writing_topics: number;
  speaking_questions: number;
  ai_requests_today: number;
};

const AdminOverview = () => {
  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      setError(null);
      try {
        const data = await fetchJson<OverviewStats>('/api/admin/overview');
        setStats(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load overview');
      }
    };
    load();
  }, []);

  const cards = [
    { label: 'Total Users', value: stats?.total_users ?? 0, icon: Users },
    { label: 'Active Writing Topics', value: stats?.writing_topics ?? 0, icon: PenTool },
    { label: 'Active Speaking Questions', value: stats?.speaking_questions ?? 0, icon: Mic },
    { label: 'Total AI Requests', value: stats?.ai_requests_today ?? 0, icon: Bot },
  ];

  return (
    <AdminLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-heading font-bold text-foreground">Dashboard Overview</h1>
          <p className="text-muted-foreground text-sm mt-1">Live platform stats</p>
          {error && <p className="text-sm text-destructive mt-2">{error}</p>}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {cards.map((stat) => (
            <Card key={stat.label}>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">{stat.label}</CardTitle>
                <stat.icon className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-foreground">{stat.value}</div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </AdminLayout>
  );
};

export default AdminOverview;
