import express from 'express';
import { getLegalDoc, updateLegalDoc } from '../controllers/legal.controller.js';
const router = express.Router();

// Public routes
router.get('/:type', getLegalDoc); // /api/legal/privacy or /api/legal/terms

// Protected admin route (add real auth middleware)
router.post('/update', updateLegalDoc);

export default router;
