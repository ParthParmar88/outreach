import type { SvgIconComponent } from "@mui/icons-material";

import ChatIcon from "@mui/icons-material/ChatBubbleOutline";
import ForumIcon from "@mui/icons-material/ForumOutlined";
import GitHubIcon from "@mui/icons-material/GitHub";
import GroupsIcon from "@mui/icons-material/Groups";
import InstagramIcon from "@mui/icons-material/Instagram";
import LinkedInIcon from "@mui/icons-material/LinkedIn";
import MailIcon from "@mui/icons-material/MailOutline";
import PodcastsIcon from "@mui/icons-material/Podcasts";
import PublicIcon from "@mui/icons-material/PublicOutlined";
import RedditIcon from "@mui/icons-material/Reddit";
import XIcon from "@mui/icons-material/X";
import YouTubeIcon from "@mui/icons-material/YouTube";

/**
 * A face for each platform.
 *
 * The planner invents its own keys, so this is a best-effort match on
 * whatever it returned rather than a closed list. Anything unrecognised
 * gets the globe, which reads as "a place on the internet" and is never
 * wrong — far better than showing nothing and leaving every card
 * identical to every other card.
 */
const BY_KEY: Record<string, SvgIconComponent> = {
  github: GitHubIcon,
  gitlab: GitHubIcon,
  hackernews: ForumIcon,
  hn: ForumIcon,
  reddit: RedditIcon,
  stackoverflow: ForumIcon,
  discourse: ForumIcon,
  forum: ForumIcon,
  slack: ChatIcon,
  discord: ChatIcon,
  whatsapp: ChatIcon,
  telegram: ChatIcon,
  linkedin: LinkedInIcon,
  x: XIcon,
  twitter: XIcon,
  bluesky: XIcon,
  mastodon: XIcon,
  instagram: InstagramIcon,
  tiktok: InstagramIcon,
  facebook: GroupsIcon,
  youtube: YouTubeIcon,
  podcast: PodcastsIcon,
  podcasts: PodcastsIcon,
  newsletter: MailIcon,
  email: MailIcon,
  meetup: GroupsIcon,
  community: GroupsIcon,
  communities: GroupsIcon,
  events: GroupsIcon,
  conference: GroupsIcon,
  blog: PublicIcon,
  seo: PublicIcon,
  producthunt: PublicIcon,
};

export function platformIcon(key: string, name: string): SvgIconComponent {
  // Try the key first, then the display name, because the planner is
  // inconsistent about which one carries the recognisable word.
  const candidates = [key, name].map((s) => (s || "").toLowerCase().replace(/[^a-z]/g, ""));
  for (const candidate of candidates) {
    if (candidate && BY_KEY[candidate]) return BY_KEY[candidate];
  }
  // Then a loose contains, so "reddit communities" still finds Reddit.
  // Only needles of four letters or more, because "x" is a key here and
  // would otherwise match roughly every word in the language.
  for (const candidate of candidates) {
    for (const [needle, icon] of Object.entries(BY_KEY)) {
      if (needle.length >= 4 && candidate.includes(needle)) return icon;
    }
  }
  return PublicIcon;
}
