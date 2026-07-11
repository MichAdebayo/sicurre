import { z } from "zod";

export const loginSchema = z.object({
  email: z.string().email("Adresse email invalide"),
  password: z.string().min(6, "Le mot de passe doit comporter au moins 6 caractères")
});

export const signUpSchema = z.object({
  name: z.string().min(2, "Le nom doit comporter au moins 2 caractères"),
  email: z.string().email("Adresse email invalide"),
  password: z.string().min(6, "Le mot de passe doit comporter au moins 6 caractères")
});

export const settingsSchema = z.object({
  apiKey: z.string().min(1, "La clé d'API est requise"),
  apiUrl: z.string().url("URL de l'API d'inférence invalide"),
  schedulerEnabled: z.boolean(),
  schedulerInterval: z.number().min(60, "L'intervalle doit être d'au moins 60 secondes")
});
