FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive TZ=Asia/Ho_Chi_Minh

RUN apt update && \
    apt install -y \
        tzdata apache2 php libapache2-mod-php php-mysql curl wget && \
    ln -fs /usr/share/zoneinfo/$TZ /etc/localtime && \
    dpkg-reconfigure --frontend noninteractive tzdata && \
    a2enmod rewrite && \
    apt clean && \
    rm -rf /var/lib/apt/lists/* /tmp/*
    
# Copy web source code
COPY ./src /var/www/html

# Set proper permissions
RUN chown -R root:www-data /var/www/html && \
    chmod 750 /var/www/html && \
    find /var/www/html -type f -exec chmod 640 {} \; && \
    find /var/www/html -type d -exec chmod 750 {} \;

WORKDIR /var/www/html

CMD ["apachectl", "-D", "FOREGROUND"]
