import {defineConfig} from "@playwright/test";
import base from "./playwright.config.mjs";
export default defineConfig({...base,testIgnore:[],testMatch:"backups.spec.mjs"});
