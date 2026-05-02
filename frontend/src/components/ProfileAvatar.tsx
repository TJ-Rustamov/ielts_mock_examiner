import { useState, useRef } from 'react';
import { motion } from 'framer-motion';
import { Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
const avatars = ['🦊', '🐼', '🦁', '🐸', '🦉', '🐺', '🦄', '🐲', '🦋', '🐢', '🦜', '🐙', '🐳', '🦈', '🐨', '🐯'];

interface ProfileAvatarProps {
  selected: string;
  onSelect: (avatar: string) => void;
}

const ProfileAvatar = ({ selected, onSelect }: ProfileAvatarProps) => {
  const onSelectFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const reader = new FileReader();
      reader.addEventListener('load', () => {
        if (reader.result) {
          onSelect(reader.result.toString());
        }
      });
      reader.readAsDataURL(e.target.files[0]);
    }
  };

  return (
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
      
      <label>
        <Button variant="outline" size="sm" className="gap-2" asChild>
          <span>
            <Upload className="h-4 w-4" /> Upload Custom Image/GIF
          </span>
        </Button>
        <input type="file" accept="image/*" onChange={onSelectFile} className="hidden" />
      </label>
    </motion.div>
  );
};

export default ProfileAvatar;
