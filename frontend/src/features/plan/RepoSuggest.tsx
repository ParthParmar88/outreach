import { useState } from "react";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import AddIcon from "@mui/icons-material/Add";
import CheckIcon from "@mui/icons-material/Check";
import TravelExploreIcon from "@mui/icons-material/TravelExplore";

import { productApi, type RepoSuggestion } from "@/lib/productApi";
import { MONO } from "@/styles/theme";

interface Props {
  /** Seeds the search box. Usually the product's domain. */
  topic: string;
  /** Already on the card, so they can be shown as added rather than offered. */
  current: string[];
  onAdd: (fullName: string) => void;
}

/**
 * Repositories GitHub actually has, rather than ones a model remembered.
 *
 * The planner produced `microsoft/DeepSpeed` (moved organisation),
 * `haystack-ai/haystack` (never existed) and `facebookresearch/detectron2`
 * (real, popular, and about object detection). All three are what recalling
 * names from training data looks like. GitHub knows what exists today.
 */
export default function RepoSuggest({ topic, current, onAdd }: Props) {
  const [query, setQuery] = useState(topic);
  const [results, setResults] = useState<RepoSuggestion[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const search = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      setResults(await productApi.suggestRepos(query.trim()));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const already = new Set(current.map((c) => c.toLowerCase()));

  return (
    <Box>
      <Stack direction="row" gap={1} alignItems="flex-start">
        <TextField
          size="small"
          fullWidth
          value={query}
          placeholder="vector database"
          label="Find repositories"
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void search();
            }
          }}
          slotProps={{
            input: {
              sx: { fontSize: 13, bgcolor: "background.paper" },
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton size="small" onClick={search} disabled={loading}>
                    {loading ? (
                      <CircularProgress size={16} />
                    ) : (
                      <TravelExploreIcon fontSize="small" />
                    )}
                  </IconButton>
                </InputAdornment>
              ),
            },
          }}
        />
      </Stack>

      {error && (
        <Typography variant="caption" color="error" sx={{ mt: 1, display: "block" }}>
          {error}
        </Typography>
      )}

      {results && results.length === 0 && (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
          Nothing found. Try a broader topic.
        </Typography>
      )}

      {results && results.length > 0 && (
        <Stack gap={0.5} sx={{ mt: 1.5, maxHeight: 260, overflowY: "auto" }}>
          {results.map((repo) => {
            const added = already.has(repo.full_name.toLowerCase());
            return (
              <Stack
                key={repo.full_name}
                direction="row"
                alignItems="center"
                gap={1}
                sx={{
                  py: 0.5,
                  px: 1,
                  borderRadius: 1,
                  "&:hover": { bgcolor: "action.hover" },
                }}
              >
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography sx={{ fontFamily: MONO, fontSize: 12 }} noWrap>
                    {repo.full_name}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" noWrap sx={{ display: "block" }}>
                    {repo.stars.toLocaleString()} stars ·{" "}
                    {/* Open issues is the number that matters here: a
                        repository with none has nobody asking for help in it,
                        however many stars it has. */}
                    {repo.open_issues.toLocaleString()} open issues
                  </Typography>
                </Box>
                <Button
                  size="small"
                  disabled={added}
                  startIcon={added ? <CheckIcon /> : <AddIcon />}
                  onClick={() => onAdd(repo.full_name)}
                >
                  {added ? "Added" : "Add"}
                </Button>
              </Stack>
            );
          })}
        </Stack>
      )}
    </Box>
  );
}
