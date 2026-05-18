import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { User, Trash2, Settings2, Shield } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import Layout from '@/components/Layout';
import ProfileAvatar from '@/components/ProfileAvatar';
import { useToast } from '@/hooks/use-toast';
import { getAuthToken, getCurrentUser, logoutLocal } from '@/lib/auth';
import { fetchJson } from '@/lib/backend';

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.08 } },
};
const item = {
  hidden: { opacity: 0, y: 15 },
  show: { opacity: 1, y: 0 },
};

const Settings = () => {
  const { toast } = useToast();
  const token = getAuthToken();
  const user = getCurrentUser() as any;
  const logout = () => {
    logoutLocal();
    window.location.href = '/';
  };
  const [selectedAvatar, setSelectedAvatar] = useState(user?.avatar || '??');
  const [showAvatarPicker, setShowAvatarPicker] = useState(false);

  const handleUpdateAvatar = async (avatar: string) => {
    setSelectedAvatar(avatar);
    setShowAvatarPicker(false);
    try {
      await fetchJson('/api/auth/update-avatar', {
        method: 'POST',
        body: JSON.stringify({ avatar_url: avatar })
      });
      toast({ title: 'Avatar updated successfully' });
      // Update local storage user data
      const user = getCurrentUser();
      if (user) {
        localStorage.setItem('auth_user', JSON.stringify({ ...user, avatar }));
      }
    } catch (e: any) {
      toast({ title: e.message, variant: 'destructive' });
    }
  };

  const [newUsername, setNewUsername] = useState('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isCurrentPasswordCorrect, setIsCurrentPasswordCorrect] = useState<boolean | null>(null);
  const [isCheckingPassword, setIsCheckingPassword] = useState(false);

  const [isUpdatingUsername, setIsUpdatingUsername] = useState(false);
  const [isUpdatingPassword, setIsUpdatingPassword] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    const checkPassword = async () => {
      if (!currentPassword) {
        setIsCurrentPasswordCorrect(null);
        return;
      }
      setIsCheckingPassword(true);
      try {
        const res = await fetchJson('/api/auth/check-password', {
          method: 'POST',
          body: JSON.stringify({ password: currentPassword })
        });
        setIsCurrentPasswordCorrect((res as any).valid);
      } catch (e) {
        setIsCurrentPasswordCorrect(false);
      } finally {
        setIsCheckingPassword(false);
      }
    };
    
    const timeoutId = setTimeout(checkPassword, 500);
    return () => clearTimeout(timeoutId);
  }, [currentPassword]);

  const handleUpdateUsername = async () => {
    if (!newUsername) return toast({ title: 'Username cannot be empty', variant: 'destructive' });
    setIsUpdatingUsername(true);
    try {
      await fetchJson('/api/auth/update-username', {
        method: 'POST',
        body: JSON.stringify({ username: newUsername })
      });
      toast({ title: 'Username updated! Please re-login.' });
      setTimeout(logout, 1500);
    } catch (e: any) {
      toast({ title: e.message, variant: 'destructive' });
    } finally {
      setIsUpdatingUsername(false);
    }
  };

  const handleUpdatePassword = async () => {
    if (!currentPassword || !newPassword || !confirmPassword) return toast({ title: 'Please fill all password fields', variant: 'destructive' });
    if (newPassword !== confirmPassword) return toast({ title: 'New passwords do not match', variant: 'destructive' });
    setIsUpdatingPassword(true);
    try {
      await fetchJson('/api/auth/update-password', {
        method: 'POST',
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword })
      });
      toast({ title: 'Password updated successfully' });
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (e: any) {
      toast({ title: e.message, variant: 'destructive' });
    } finally {
      setIsUpdatingPassword(false);
    }
  };

  const handleDeleteAccount = async () => {
    if (!confirm('Are you absolutely sure you want to delete your account? This action cannot be undone.')) return;
    setIsDeleting(true);
    try {
      await fetchJson('/api/auth/delete-account', {
        method: 'POST',
      });
      toast({ title: 'Account deleted' });
      setTimeout(logout, 1000);
    } catch (e: any) {
      toast({ title: e.message, variant: 'destructive' });
      setIsDeleting(false);
    }
  };

  return (
    <Layout>
      <div className="container mx-auto px-4 py-8 max-w-2xl relative">
        <div className="absolute w-72 h-72 bg-primary/5 rounded-full blur-3xl -top-20 -right-20 pointer-events-none" />

        <motion.div variants={container} initial="hidden" animate="show" className="relative z-10">
          <motion.div variants={item} className="flex items-center gap-3 mb-8">
            <div className="p-2 rounded-xl bg-primary/10">
              <Settings2 className="h-6 w-6 text-primary" />
            </div>
            <h1 className="text-3xl font-bold text-foreground">Settings</h1>
          </motion.div>

          <motion.div variants={item}>
            <Card className="mb-6 overflow-hidden group hover:glow-sm transition-shadow">
              <CardHeader>
                <CardTitle>Profile Picture</CardTitle>
                <CardDescription>Choose an avatar or upload a custom picture</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-4">
                  <motion.div
                    whileHover={{ scale: 1.1, rotate: 5 }}
                    whileTap={{ scale: 0.95 }}
                    className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center text-4xl cursor-pointer hover:bg-primary/20 transition-colors glow-sm overflow-hidden"
                    onClick={() => setShowAvatarPicker(!showAvatarPicker)}
                  >
                    {selectedAvatar.length > 10 ? <img src={selectedAvatar} alt="avatar" className="w-full h-full object-cover" /> : selectedAvatar}
                  </motion.div>
                  <Button variant="outline" onClick={() => setShowAvatarPicker(!showAvatarPicker)}>
                    Change Avatar
                  </Button>
                </div>
                {showAvatarPicker && (
                  <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}>
                    <ProfileAvatar selected={selectedAvatar} onSelect={handleUpdateAvatar} />
                  </motion.div>
                )}
              </CardContent>
            </Card>
          </motion.div>


          <motion.div variants={item}>
            <Card className="mb-6 hover:glow-sm transition-shadow">
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><User className="h-5 w-5 text-primary" /> Username</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="text-sm text-muted-foreground mb-2">Current username: <strong className="text-foreground">{user?.username}</strong></div>
                <Input placeholder="New username" value={newUsername} onChange={(e) => setNewUsername(e.target.value)} />
                <Button className="glow-sm" onClick={handleUpdateUsername} disabled={isUpdatingUsername}>
                  {isUpdatingUsername ? 'Updating...' : 'Update Username'}
                </Button>
              </CardContent>
            </Card>
          </motion.div>

          <motion.div variants={item}>
            <Card className="mb-6 hover:glow-sm transition-shadow">
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><Shield className="h-5 w-5 text-primary" /> Change Password</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Input type="password" placeholder="Current password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
                  {isCurrentPasswordCorrect === true && (
                    <div className="text-green-500 text-sm mt-1">Correct password</div>
                  )}
                  {isCurrentPasswordCorrect === false && currentPassword && !isCheckingPassword && (
                    <div className="text-red-500 text-sm mt-1">Incorrect password</div>
                  )}
                  {isCheckingPassword && <div className="text-muted-foreground text-sm mt-1">Checking...</div>}
                </div>
                
                <Input 
                  type="password" 
                  placeholder="New password" 
                  value={newPassword} 
                  onChange={(e) => setNewPassword(e.target.value)} 
                  disabled={!isCurrentPasswordCorrect}
                />
                <Input 
                  type="password" 
                  placeholder="Confirm new password" 
                  value={confirmPassword} 
                  onChange={(e) => setConfirmPassword(e.target.value)} 
                  disabled={!isCurrentPasswordCorrect}
                />
                
                <Button className="glow-sm" onClick={handleUpdatePassword} disabled={isUpdatingPassword || !isCurrentPasswordCorrect}>
                  {isUpdatingPassword ? 'Updating...' : 'Update Password'}
                </Button>
              </CardContent>
            </Card>
          </motion.div>

          <motion.div variants={item}>
            <Card className="border-destructive/30 overflow-hidden relative group">
              <div className="absolute inset-0 bg-gradient-to-br from-destructive/5 to-transparent pointer-events-none" />
              <CardHeader className="relative z-10">
                <CardTitle className="flex items-center gap-2 text-destructive"><Trash2 className="h-5 w-5" /> Danger Zone</CardTitle>
                <CardDescription>Permanently delete your account and all data</CardDescription>
              </CardHeader>
              <CardContent className="relative z-10">
                <Button variant="destructive" onClick={handleDeleteAccount} disabled={isDeleting}>
                  {isDeleting ? 'Deleting...' : 'Delete Account'}
                </Button>
              </CardContent>
            </Card>
          </motion.div>
        </motion.div>
      </div>
    </Layout>
  );
};

export default Settings;