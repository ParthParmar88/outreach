import { useEffect } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import FormControl from "@mui/material/FormControl";
import FormHelperText from "@mui/material/FormHelperText";
import InputLabel from "@mui/material/InputLabel";
import ListItemText from "@mui/material/ListItemText";
import MenuItem from "@mui/material/MenuItem";
import OutlinedInput from "@mui/material/OutlinedInput";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { useKeywordSuggestions } from "./useKeywordSuggestions";
import type { BriefInput, DaysBack, SourceId } from "@/lib/types";
import {
  DATE_OPTIONS,
  DESCRIPTION_MIN,
  FIELD_COPY,
  SOURCE_OPTIONS,
  VALIDATION_COPY,
} from "./fields";
import { useBriefDraft } from "./useBriefDraft";

const schema = z.object({
  productName: z.string().trim().min(2, VALIDATION_COPY.productName),
  productUrl: z.string().trim().url(VALIDATION_COPY.productUrl),
  description: z.string().trim().min(DESCRIPTION_MIN, VALIDATION_COPY.description),
  keywords: z.array(z.string()).min(1, VALIDATION_COPY.keywords),
  sources: z.array(z.string()).min(1, VALIDATION_COPY.sources),
  daysBack: z.number(),
});

type FormValues = z.infer<typeof schema>;

interface Props {
  submitting: boolean;
  onSubmit: (brief: BriefInput) => void;
}

export default function BriefForm({ submitting, onSubmit }: Props) {
  const { load, save } = useBriefDraft();

  const {
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: load(),
  });

  // Autosave, so a refresh never costs anyone their brief.
  const watched = useWatch({ control });
  useEffect(() => {
    save(watched as Partial<BriefInput>);
  }, [watched, save]);

  // Suggestions follow what they have described, rather than a list checked
  // into the repository for one particular product.
  const { options: keywordOptions, loading: keywordsLoading } =
    useKeywordSuggestions((watched.description as string) ?? "");

  const submit = (values: FormValues) =>
    onSubmit({
      ...values,
      sources: values.sources as SourceId[],
      daysBack: values.daysBack as DaysBack,
    });

  return (
    <Paper
      variant="outlined"
      component="form"
      noValidate
      onSubmit={handleSubmit(submit)}
      sx={{ p: { xs: 2.5, md: 4 } }}
    >
      <Stack spacing={3.5}>
        {/* ---- the product ---- */}
        <Box>
          <Typography variant="subtitle2" sx={{ mb: 2 }}>
            Your product
          </Typography>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <Controller
              name="productName"
              control={control}
              render={({ field }) => (
                <TextField
                  {...field}
                  label={FIELD_COPY.productName.label}
                  placeholder={FIELD_COPY.productName.placeholder}
                  error={Boolean(errors.productName)}
                  helperText={errors.productName?.message ?? FIELD_COPY.productName.help}
                />
              )}
            />
            <Controller
              name="productUrl"
              control={control}
              render={({ field }) => (
                <TextField
                  {...field}
                  label={FIELD_COPY.productUrl.label}
                  placeholder={FIELD_COPY.productUrl.placeholder}
                  error={Boolean(errors.productUrl)}
                  helperText={errors.productUrl?.message ?? FIELD_COPY.productUrl.help}
                />
              )}
            />
          </Stack>
        </Box>

        <Divider />

        {/* ---- what they want ---- */}
        <Controller
          name="description"
          control={control}
          render={({ field }) => (
            <TextField
              {...field}
              label={FIELD_COPY.description.label}
              placeholder={FIELD_COPY.description.placeholder}
              multiline
              minRows={3}
              error={Boolean(errors.description)}
              helperText={errors.description?.message ?? FIELD_COPY.description.help}
            />
          )}
        />

        <Controller
          name="keywords"
          control={control}
          render={({ field }) => (
            <Autocomplete
              multiple
              freeSolo
              options={keywordOptions}
              loading={keywordsLoading}
              noOptionsText={
                keywordsLoading
                  ? "Thinking of keywords…"
                  : "Describe what you are looking for above, and suggestions appear here. You can type your own at any time."
              }
              value={field.value}
              onChange={(_, next) => {
                const seen = new Set<string>();
                const cleaned: string[] = [];
                for (const raw of next as string[]) {
                  const word = raw.trim();
                  if (!word) continue;
                  const key = word.toLowerCase();
                  if (seen.has(key)) continue;
                  seen.add(key);
                  cleaned.push(word);
                }
                field.onChange(cleaned);
              }}
              renderTags={(tags, getTagProps) =>
                tags.map((tag, index) => {
                  const { key, ...chipProps } = getTagProps({ index });
                  return (
                    <Chip
                      key={key}
                      {...chipProps}
                      label={tag}
                      size="small"
                      color="primary"
                      variant="outlined"
                    />
                  );
                })
              }
              renderInput={(params) => (
                <TextField
                  {...params}
                  label={FIELD_COPY.keywords.label}
                  placeholder={FIELD_COPY.keywords.placeholder}
                  error={Boolean(errors.keywords)}
                  helperText={errors.keywords?.message ?? FIELD_COPY.keywords.help}
                />
              )}
            />
          )}
        />

        <Divider />

        {/* ---- predicates: what the user declares ---- */}
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
          <Controller
            name="sources"
            control={control}
            render={({ field }) => (
              <FormControl fullWidth size="small" error={Boolean(errors.sources)}>
                <InputLabel id="sources-label">{FIELD_COPY.sources.label}</InputLabel>
                <Select
                  {...field}
                  multiple
                  labelId="sources-label"
                  input={<OutlinedInput label={FIELD_COPY.sources.label} />}
                  renderValue={(selected) => (
                    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                      {(selected as string[]).map((id) => (
                        <Chip
                          key={id}
                          size="small"
                          label={SOURCE_OPTIONS.find((s) => s.id === id)?.label ?? id}
                        />
                      ))}
                    </Box>
                  )}
                >
                  {SOURCE_OPTIONS.map((source) => (
                    <MenuItem key={source.id} value={source.id} disabled={source.disabled}>
                      <Checkbox size="small" checked={field.value.includes(source.id)} />
                      <ListItemText primary={source.label} secondary={source.reason} />
                    </MenuItem>
                  ))}
                </Select>
                <FormHelperText>
                  {errors.sources?.message ?? FIELD_COPY.sources.help}
                </FormHelperText>
              </FormControl>
            )}
          />

          <Controller
            name="daysBack"
            control={control}
            render={({ field }) => (
              <FormControl fullWidth size="small">
                <InputLabel id="days-label">{FIELD_COPY.daysBack.label}</InputLabel>
                <Select
                  {...field}
                  labelId="days-label"
                  label={FIELD_COPY.daysBack.label}
                  onChange={(e) => field.onChange(Number(e.target.value))}
                >
                  {DATE_OPTIONS.map((option) => (
                    <MenuItem key={option.value} value={option.value}>
                      {option.label}
                    </MenuItem>
                  ))}
                </Select>
                <FormHelperText>{FIELD_COPY.daysBack.help}</FormHelperText>
              </FormControl>
            )}
          />
        </Stack>

        <Divider />

        <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems={{ sm: "center" }}>
          <Button type="submit" variant="contained" size="large" disabled={submitting}>
            {submitting ? "Compiling…" : "Start search"}
          </Button>
          <Typography variant="caption" color="text.secondary">
            Next you review the compiled plan. Nothing runs until you approve it.
          </Typography>
        </Stack>
      </Stack>
    </Paper>
  );
}
