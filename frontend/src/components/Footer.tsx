import { Link } from 'react-router-dom';
import { Sparkles } from 'lucide-react';

const Footer = () => (
  <footer className="bg-card/80 backdrop-blur-sm border-t mt-auto relative overflow-hidden">
    <div className="absolute w-96 h-96 bg-primary/3 rounded-full blur-3xl -bottom-40 -right-40 pointer-events-none" />
    <div className="container mx-auto px-4 py-12 relative z-10">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
        <div>
          <h3 className="font-heading font-semibold text-foreground mb-3 flex items-center gap-1.5">
            <Sparkles className="h-4 w-4 text-primary" /> Product
          </h3>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li><Link to="/pricing" className="hover:text-primary transition-colors">Pricing</Link></li>
            <li><a href="#" className="hover:text-primary transition-colors">Features</a></li>
            <li><a href="#" className="hover:text-primary transition-colors">Updates</a></li>
          </ul>
        </div>
        <div>
          <h3 className="font-heading font-semibold text-foreground mb-3">Support</h3>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li><a href="#" className="hover:text-primary transition-colors">Help Center</a></li>
            <li><a href="#" className="hover:text-primary transition-colors">Contact Us</a></li>
            <li><a href="#" className="hover:text-primary transition-colors">FAQ</a></li>
          </ul>
        </div>
        <div>
          <h3 className="font-heading font-semibold text-foreground mb-3">Company</h3>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li><a href="#" className="hover:text-primary transition-colors">About Us</a></li>
            <li><a href="#" className="hover:text-primary transition-colors">Careers</a></li>
            <li><a href="#" className="hover:text-primary transition-colors">Blog</a></li>
          </ul>
        </div>
        <div>
          <h3 className="font-heading font-semibold text-foreground mb-3">Legal</h3>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li><a href="#" className="hover:text-primary transition-colors">Privacy Policy</a></li>
            <li><a href="#" className="hover:text-primary transition-colors">Terms of Service</a></li>
            <li><a href="#" className="hover:text-primary transition-colors">Cookie Policy</a></li>
          </ul>
        </div>
      </div>
      <div className="border-t mt-8 pt-8 flex flex-col md:flex-row items-center justify-between gap-4">
        <p className="text-sm text-muted-foreground">© 2026 <span className="font-semibold text-foreground">IELTS Mastery</span>. All rights reserved.</p>
        <p className="text-sm text-muted-foreground">123 Education Street, London, UK</p>
      </div>
    </div>
  </footer>
);

export default Footer;
