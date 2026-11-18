# ==================================
# ETAPA 1: COMPILAR ANGULAR
# ==================================

FROM node:26-alpine AS build

WORKDIR /app

# Copiar archivos de dependencias
COPY package*.json ./

# Instalar dependencias
RUN npm ci

# Copiar código fuente
COPY . .

# Compilar Angular para producción
RUN npm run build -- --configuration production


# ==================================
# ETAPA 2: SERVIR CON NGINX
# ==================================

FROM nginx:alpine

# Configuración personalizada
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copiar compilación de Angular
COPY --from=build /app/dist/datamind-ui/browser/ /usr/share/nginx/html/

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]