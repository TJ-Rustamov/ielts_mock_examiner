import { motion } from 'framer-motion';
import { Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';

const avatars = ['🦊', '🐼', '🦁', '🐸', '🦉', '🐺', '🦄', '🐲', '🦋', '🐢', '🦜', '🐙', '🐳', '🦈', '🐨', '🐯'];

interface ProfileAvatarProps {
  selected: string;
  onSelect: (avatar: string) => void;
}

const ProfileAvatar = ({ selected, onSelect }: ProfileAvatarProps) => (
  <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="mt-4">
    <div className="grid grid-cols-8 gap-2 mb-4">
      {avatars.map(a => (
        <button
          key={a}
          onClick={() => onSelect(a)}
          className={`text-2xl p-2 rounded-lg transition-all ${
            selected === a ? 'bg-primary/20 ring-2 ring-primary' : 'hover:bg-muted'
          }`}
        >
          {a}
        </button>
      ))}
    </div>
    <Button variant="outline" size="sm" className="gap-2">
      <Upload className="h-4 w-4" /> Upload Custom
    </Button>
  </motion.div>
);

export default ProfileAvatar;
