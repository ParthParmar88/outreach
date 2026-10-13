import { httpApi, type Api } from "./api";

/**
 * The backend.
 *
 * There used to be an in-browser fake here so screens could be built before
 * FastAPI answered. It answers now, so the fake is gone: two implementations
 * of one interface means every new field has to be added twice, and the one
 * nobody is looking at drifts. A drifted mock is worse than none, because it
 * makes a screen look right while it is wrong.
 */
export const api: Api = httpApi;
