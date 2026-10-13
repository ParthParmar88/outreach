import { Link as RouterLink } from "react-router-dom";

import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";

/**
 * A run that finds nothing is a real answer, not a failure. Never pad the
 * list to look busy.
 */
export default function EmptyState() {
  return (
    <Paper variant="outlined" sx={{ p: 5, textAlign: "center" }}>
      <Typography variant="h6" sx={{ mb: 1 }}>
        Nothing came back
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ maxWidth: "46ch", mx: "auto", mb: 3 }}>
        The run finished and no conversation was worth showing. Try a wider date
        window, or drop your narrowest term and compile the plan again.
      </Typography>
      <Button component={RouterLink} to="/new" variant="outlined">
        Change the brief
      </Button>
    </Paper>
  );
}
