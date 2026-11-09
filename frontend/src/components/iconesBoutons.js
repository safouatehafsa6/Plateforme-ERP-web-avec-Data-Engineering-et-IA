import {
  Bell, Bot, Headset, MessageCircle, LogIn, UserPlus, Moon, Globe, Phone, Mail, CircleQuestionMark, Info, Star, Heart,
  ShoppingCart, FileText, Calculator, Video, Users, Settings, Calendar, Zap, Gift, Megaphone, BookOpen, LifeBuoy, Link2,
  ExternalLink, House, Search, Sparkles, CreditCard, ShieldCheck, Bookmark,
} from "lucide-react";

// Noms stockés par l'API (liste blanche) → composants d'icône. Un nom inconnu retombe sur « Info ».
export const ICONES_LUCIDE = {
  bell: Bell, bot: Bot, headset: Headset, "message-circle": MessageCircle, "log-in": LogIn, "user-plus": UserPlus, moon: Moon,
  globe: Globe, phone: Phone, mail: Mail, "help-circle": CircleQuestionMark, info: Info, star: Star, heart: Heart,
  "shopping-cart": ShoppingCart, "file-text": FileText, calculator: Calculator, video: Video, users: Users, settings: Settings,
  calendar: Calendar, zap: Zap, gift: Gift, megaphone: Megaphone, "book-open": BookOpen, "life-buoy": LifeBuoy, link: Link2,
  "external-link": ExternalLink, home: House, search: Search, sparkles: Sparkles, "credit-card": CreditCard,
  "shield-check": ShieldCheck, bookmark: Bookmark,
};

export function iconeBouton(nom) {
  return ICONES_LUCIDE[nom] || Info;
}
