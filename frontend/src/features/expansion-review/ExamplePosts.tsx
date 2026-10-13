import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { SOURCE_LABEL } from "@/lib/format";
import type { ExamplePost } from "@/lib/types";

/**
 * Nobody can review a search plan. Anyone can read a post and say "yes,
 * that is exactly it" or "no, that is not what I meant". Fifteen seconds
 * here is the difference between a trusted tool and a black box.
 */
export default function ExamplePosts({ posts }: { posts: ExamplePost[] }) {
  return (
    <Stack spacing={1.5}>
      {posts.map((post) => (
        <Paper key={post.title} variant="outlined" sx={{ p: 2.25 }}>
          <Typography variant="caption" color="text.secondary">
            {SOURCE_LABEL[post.source]}
          </Typography>
          <Typography sx={{ fontWeight: 620, fontSize: 14.5, mt: 0.25, mb: 0.75 }}>
            {post.title}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {post.body}
          </Typography>
        </Paper>
      ))}
    </Stack>
  );
}
