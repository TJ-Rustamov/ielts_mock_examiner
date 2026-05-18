import { useEffect, useMemo, useState } from 'react';
import AdminLayout from '@/components/admin/AdminLayout';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from '@/components/ui/dialog';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { KeyRound, MoreVertical, Search, Trash2, UserPlus, AlertTriangle } from 'lucide-react';
import { fetchJson } from '@/lib/backend';

type AdminUser = {
  id: number;
  username: string;
  email: string;
  is_staff: boolean;
  is_superuser: boolean;
  is_active: boolean;
  date_joined: string;
  writing_tests: number;
  speaking_tests: number;
};

const UserManagement = () => {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [newUser, setNewUser] = useState({ username: '', email: '', password: '' });

  const [resetPasswordUser, setResetPasswordUser] = useState<AdminUser | null>(null);
  const [newPassword, setNewPassword] = useState('');

  const [deleteUser, setDeleteUser] = useState<AdminUser | null>(null);

  const loadUsers = async (term = '') => {
    setLoading(true);
    setError(null);
    try {
      const query = term ? `?search=${encodeURIComponent(term)}` : '';
      const data = await fetchJson<{ results: AdminUser[] }>(`/api/admin/users${query}`);
      setUsers(data.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
  }, []);

  const filtered = useMemo(() => {
    if (!search.trim()) return users;
    const q = search.toLowerCase();
    return users.filter((u) => u.username.toLowerCase().includes(q) || (u.email || '').toLowerCase().includes(q));
  }, [users, search]);

  const handleAddUser = async () => {
    setError(null);
    try {
      const created = await fetchJson<AdminUser>('/api/admin/users', {
        method: 'POST',
        body: JSON.stringify({
          username: newUser.username,
          email: newUser.email,
          password: newUser.password,
          is_staff: false,
        }),
      });
      setUsers((prev) => [created, ...prev]);
      setIsAddOpen(false);
      setNewUser({ username: '', email: '', password: '' });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create user');
    }
  };

  const patchUser = async (userId: number, payload: Record<string, unknown>) => {
    setError(null);
    try {
      const updated = await fetchJson<AdminUser>(`/api/admin/users/${userId}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      });
      setUsers((prev) => prev.map((u) => (u.id === userId ? updated : u)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update user');
    }
  };

  const handleResetPassword = async () => {
    if (!resetPasswordUser || !newPassword) return;
    await patchUser(resetPasswordUser.id, { password: newPassword });
    setResetPasswordUser(null);
    setNewPassword('');
  };

  const handleDelete = async (userId: number) => {
    setError(null);
    try {
      await fetchJson<{}>(`/api/admin/users/${userId}`, { method: 'DELETE' });
      setUsers((prev) => prev.filter((u) => u.id !== userId));
      setDeleteUser(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete user');
    }
  };

  return (
    <AdminLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-heading font-bold text-foreground">User Management</h1>
            <p className="text-muted-foreground text-sm mt-1">{users.length} total users</p>
          </div>
          <Dialog open={isAddOpen} onOpenChange={setIsAddOpen}>
            <DialogTrigger asChild>
              <Button>
                <UserPlus className="h-4 w-4 mr-2" />Add User
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Create User</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 mt-2">
                <Input placeholder="Username" value={newUser.username} onChange={(e) => setNewUser((p) => ({ ...p, username: e.target.value }))} />
                <Input placeholder="Email (optional)" value={newUser.email} onChange={(e) => setNewUser((p) => ({ ...p, email: e.target.value }))} />
                <Input type="password" placeholder="Password" value={newUser.password} onChange={(e) => setNewUser((p) => ({ ...p, password: e.target.value }))} />
                <Button className="w-full" onClick={handleAddUser} disabled={!newUser.username || !newUser.password}>Create</Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search users..."
            className="pl-10"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onBlur={() => loadUsers(search)}
          />
        </div>

        <div className="space-y-2">
          {loading && <p className="text-sm text-muted-foreground">Loading users...</p>}
          {!loading && filtered.length === 0 && <p className="text-sm text-muted-foreground">No users found.</p>}

          {filtered.map((user) => (
            <Card key={user.id}>
              <CardContent className="flex items-center gap-4 p-4">
                <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-sm flex-shrink-0">
                  {user.username.charAt(0).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-foreground text-sm">{user.username}</span>
                    <Badge variant={user.is_staff || user.is_superuser ? 'default' : 'secondary'} className="text-xs">
                      {user.is_staff || user.is_superuser ? 'admin' : 'user'}
                    </Badge>
                    <Badge variant={user.is_active ? 'outline' : 'destructive'} className="text-xs">
                      {user.is_active ? 'active' : 'suspended'}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {user.email || 'No email'} | Joined {new Date(user.date_joined).toLocaleDateString()} | {user.writing_tests + user.speaking_tests} tests
                  </p>
                </div>

                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" className="h-8 w-8">
                      <MoreVertical className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => patchUser(user.id, { is_active: !user.is_active })}>
                      {user.is_active ? 'Suspend' : 'Reactivate'} Account
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => patchUser(user.id, { is_staff: !(user.is_staff || user.is_superuser) })}>
                      {user.is_staff || user.is_superuser ? 'Set as User' : 'Set as Admin'}
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => { setResetPasswordUser(user); setNewPassword(''); }}>
                      <KeyRound className="h-4 w-4 mr-2" />Reset Password
                    </DropdownMenuItem>
                    <DropdownMenuItem className="text-destructive" onClick={() => setDeleteUser(user)}>
                      <Trash2 className="h-4 w-4 mr-2" />Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      <Dialog open={!!resetPasswordUser} onOpenChange={(open) => !open && setResetPasswordUser(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reset Password</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            <p className="text-sm text-muted-foreground">
              Enter a new password for <strong>{resetPasswordUser?.username}</strong>.
            </p>
            <Input 
              type="password" 
              placeholder="New Password" 
              value={newPassword} 
              onChange={(e) => setNewPassword(e.target.value)} 
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setResetPasswordUser(null)}>Cancel</Button>
            <Button onClick={handleResetPassword} disabled={!newPassword}>Reset Password</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!deleteUser} onOpenChange={(open) => !open && setDeleteUser(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center text-destructive">
              <AlertTriangle className="h-5 w-5 mr-2" /> Confirm Deletion
            </DialogTitle>
          </DialogHeader>
          <div className="mt-2">
            <p className="text-sm text-muted-foreground">
              Are you sure you want to delete user <strong>{deleteUser?.username}</strong>? This action cannot be undone.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteUser(null)}>Cancel</Button>
            <Button variant="destructive" onClick={() => deleteUser && handleDelete(deleteUser.id)}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AdminLayout>
  );
};

export default UserManagement;
